"""coherence.signal.trend — first/second differences, monotonicity, and
volatility over an arbitrary numeric series field.

This is the source-agnostic difference engine that :mod:`coherence.signal`
promises every measurement dimension: :func:`trend` walks every field in a
loaded :class:`~coherence.signal.schema.Series` (``series.field_names()``) and
reports, per field, its per-step first difference (f', velocity) and second
difference (f'', acceleration), whether the field trends monotonically, and a
simple volatility measure — with no branch on *what* the field means or which
domain produced it.

Reused difference math
-----------------------
:func:`first_difference` and :func:`second_difference` are the two pure,
sequence-in/sequence-out functions this module builds on. They are
deliberately generic (any ``Sequence[float]``, not tied to the series schema)
so a later refactor (plan task t5) can point
:mod:`coherence.meaning.trend`'s difference math at these exact functions
without changing its output: both compute the same per-step
``[s[i+1] - s[i] for i]`` difference meaning's private helper already used.

Sparse fields
-------------
The series schema allows a field to be absent from some points (see
``docs/signal-series.md``). :func:`analyze_field` computes differences over
only the points where the field is *present*, in series order, ignoring the
gap positionally — the same shape a hand-authored, non-uniform series would
need — and records a ``trend_sparse_field`` diagnostic naming how many points
(and at which index) lacked the field.

Insufficient points
--------------------
Unlike :func:`coherence.meaning.trend.trend` (which raises ``ValueError``
below two points, because the meaning CLI always has at least two artifacts
to compare), this engine never raises for a short field: an under-populated
field degrades to an explicit diagnostic and a ``null`` differences slot,
because one series field can legitimately have only one measurement while its
siblings have many.

* **0 or 1 present values** — no first difference is possible. ``first`` and
  ``second`` are both ``{"values": null, "reason": <str>}`` and a
  ``trend_too_short`` diagnostic is recorded.
* **2 present values** — ``first`` has one value; ``second`` needs a third
  point and is reported ``{"values": null, "reason": <str>}`` with a
  ``trend_second_unavailable`` diagnostic (mirroring
  ``coherence.meaning.trend``'s ``second_difference_available`` gate, just
  keyed on *present* count rather than total series length).
* **3+ present values** — both slots are populated.

Monotonicity and volatility
----------------------------
Both are derived from the field's first-difference series (so they need at
least 2 present values; ``None`` otherwise):

* ``monotonicity`` — ``"increasing"`` when every step is positive,
  ``"decreasing"`` when every step is negative, ``"constant"`` when every step
  is ~0, else ``"mixed"``. An epsilon (not ``== 0.0``) guards the zero test.
* ``volatility`` — the population standard deviation of the first-difference
  series (``statistics.pstdev``): 0.0 for a perfectly smooth trend (steady
  steps, however large), larger as the step sizes vary — a jagged or
  oscillating field is "more volatile" than a field trending steadily in one
  direction, even when both move the same total distance.

JSON output shape
------------------
:func:`trend` returns a plain, JSON-serialisable ``dict``::

    {
      "n": <int>,                 # total points in the series (not per-field)
      "domain": <str|None>,       # passthrough of Series.domain
      "fields": {
        "<field name>": {
          "n_present": <int>,     # points where this field had a value
          "first":  {"values": [<float>, ...] | null, "reason": <str|null>},
          "second": {"values": [<float>, ...] | null, "reason": <str|null>},
          "monotonicity": "increasing"|"decreasing"|"constant"|"mixed"|null,
          "volatility": <float|null>,
          "diagnostics": [{"code": str, "message": str}, ...]
        },
        ...                        # one entry per name in series.field_names(),
                                    # in sorted order for deterministic output
      },
      "diagnostics": [...]         # series.diagnostics ++ every field's own
                                    # diagnostics, flattened, in field order
    }

Accepted input
--------------
:func:`trend` accepts an already-loaded
:class:`~coherence.signal.schema.Series`, OR anything
:func:`~coherence.signal.schema.load_series` accepts (a raw mapping, or a JSON
``str``/``bytes`` payload) — it loads it first. Either way the loader's own
diagnostics (malformed values skipped, ids synthesized, ...) are carried into
the returned ``diagnostics`` list, so nothing is silently dropped just because
the caller handed over raw data instead of pre-loading it.
"""

from __future__ import annotations

import statistics
from typing import Any, Mapping, Sequence

from coherence.signal.schema import Series, load_series

# --- machine-readable diagnostic codes --------------------------------------
CODE_TREND_TOO_SHORT = "trend_too_short"
CODE_TREND_SECOND_UNAVAILABLE = "trend_second_unavailable"
CODE_TREND_SPARSE_FIELD = "trend_sparse_field"
CODE_TREND_NO_FIELDS = "trend_no_fields"

# A step at or below this magnitude is treated as "no movement" for
# monotonicity — an epsilon guard so the zero-test is never a fragile
# ``== 0.0`` floating-point comparison.
_MONOTONE_EPS = 1e-9


def _diag(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def first_difference(values: Sequence[float]) -> list[float]:
    """Return the discrete first difference ``[values[i+1] - values[i] for i]``.

    A per-step, unitless difference: the result is one shorter than ``values``
    (empty when ``values`` has fewer than two elements). This is the same
    per-step semantics :mod:`coherence.meaning.trend` uses for its score
    derivatives — generalized here to any named series field so it can be
    reused (plan task t5) instead of reimplemented.
    """
    return [values[i + 1] - values[i] for i in range(len(values) - 1)]


def second_difference(values: Sequence[float]) -> list[float]:
    """Return the discrete second difference: the first difference of the
    first-difference series.

    Two shorter than ``values`` (empty when ``values`` has fewer than three
    elements).
    """
    return first_difference(first_difference(values))


def _too_short_reason(n_present: int) -> str:
    return (
        f"first difference (f') needs at least 2 present values; got {n_present}. "
        "A first difference is undefined for a single measurement."
    )


def _second_unavailable_reason(n_present: int) -> str:
    return (
        f"second difference (f'') needs at least 3 present values; got {n_present}. "
        "A second difference is the first difference of the first-difference "
        "series, which is empty for a single step."
    )


def _first_slot(values: Sequence[float], n_present: int) -> dict[str, Any]:
    if n_present < 2:
        return {"values": None, "reason": _too_short_reason(n_present)}
    return {"values": first_difference(values), "reason": None}


def _second_slot(values: Sequence[float], n_present: int) -> dict[str, Any]:
    if n_present < 2:
        return {"values": None, "reason": _too_short_reason(n_present)}
    if n_present < 3:
        return {"values": None, "reason": _second_unavailable_reason(n_present)}
    return {"values": second_difference(values), "reason": None}


def _monotonicity(diffs: Sequence[float]) -> str | None:
    """Classify a first-difference series as increasing/decreasing/constant/mixed.

    ``None`` when there are no differences to classify (fewer than 2 present
    values). Every comparison against zero uses ``_MONOTONE_EPS`` rather than
    an exact ``== 0.0`` test.
    """
    if not diffs:
        return None
    if all(d > _MONOTONE_EPS for d in diffs):
        return "increasing"
    if all(d < -_MONOTONE_EPS for d in diffs):
        return "decreasing"
    if all(abs(d) <= _MONOTONE_EPS for d in diffs):
        return "constant"
    return "mixed"


def _volatility(diffs: Sequence[float]) -> float | None:
    """Population standard deviation of the first-difference series.

    ``None`` when there are no differences (fewer than 2 present values).
    ``0.0`` for a single step or a perfectly steady one (no variation between
    steps) — an actual population stdev of a (possibly single-element)
    sample, not a fragile zero-comparison.
    """
    if not diffs:
        return None
    return float(statistics.pstdev(diffs))


def analyze_field(series: Series, field: str) -> dict[str, Any]:
    """Analyze one named field across ``series`` — differences, monotonicity, volatility.

    Reads ``field`` from every point where it is present (``field in
    point.values``), in series order, and computes over that (possibly
    sparse) subsequence — see the module docstring for the exact output shape
    and the diagnostic codes.

    Args:
        series: A loaded :class:`~coherence.signal.schema.Series`.
        field: The value name to analyze (typically one member of
            ``series.field_names()``).

    Returns:
        A JSON-serialisable ``dict`` with ``n_present``, ``first``, ``second``,
        ``monotonicity``, ``volatility``, and this field's own ``diagnostics``.
    """
    total_n = len(series.points)
    present_points = [point for point in series.points if field in point.values]
    values = [point.values[field] for point in present_points]
    n_present = len(values)

    diagnostics: list[dict[str, str]] = []
    if n_present < 2:
        diagnostics.append(
            _diag(
                CODE_TREND_TOO_SHORT,
                f"field {field!r}: only {n_present} present value(s) across {total_n} "
                "point(s); a first difference (f') needs at least 2 -- no differences computed",
            )
        )
    elif n_present == 2:
        diagnostics.append(
            _diag(
                CODE_TREND_SECOND_UNAVAILABLE,
                f"field {field!r}: only {n_present} present value(s); a second difference "
                "(f'') needs at least 3 -- second difference not computed",
            )
        )

    missing = total_n - n_present
    if 0 < missing and n_present > 0:
        missing_indices = [point.index for point in series.points if field not in point.values]
        diagnostics.append(
            _diag(
                CODE_TREND_SPARSE_FIELD,
                f"field {field!r}: missing from {missing} of {total_n} point(s) "
                f"(indices {missing_indices}); computed over the {n_present} present value(s)",
            )
        )

    first_slot = _first_slot(values, n_present)
    second_slot = _second_slot(values, n_present)
    diffs = first_slot["values"] or []

    return {
        "n_present": n_present,
        "first": first_slot,
        "second": second_slot,
        "monotonicity": _monotonicity(diffs),
        "volatility": _volatility(diffs),
        "diagnostics": diagnostics,
    }


def trend(data: Series | Mapping[str, Any] | str | bytes) -> dict[str, Any]:
    """Compute per-field f'/f'' trend, monotonicity, and volatility for a series.

    Accepts an already-loaded :class:`~coherence.signal.schema.Series`, or
    anything :func:`~coherence.signal.schema.load_series` accepts (a raw
    mapping, or JSON ``str``/``bytes``) — loading it first. See the module
    docstring for the exact JSON output shape.

    Args:
        data: A :class:`Series`, or a raw series mapping / JSON payload.

    Returns:
        A JSON-serialisable ``dict`` (see module docstring). Never raises for
        a short or sparse field — every degraded case is an explicit
        diagnostic, not a crash.

    Raises:
        SeriesError: Propagated from
            :func:`~coherence.signal.schema.load_series` when ``data`` is not
            a ``Series`` and is structurally uninterpretable (not a mapping,
            unparseable JSON, missing ``points``, ...).
    """
    series = data if isinstance(data, Series) else load_series(data)
    diagnostics: list[dict[str, str]] = list(series.diagnostics)

    field_names = sorted(series.field_names())
    if not field_names:
        diagnostics.append(
            _diag(
                CODE_TREND_NO_FIELDS,
                "series has no numeric fields to analyze across its points",
            )
        )

    fields: dict[str, dict[str, Any]] = {}
    for name in field_names:
        result = analyze_field(series, name)
        fields[name] = result
        diagnostics.extend(result["diagnostics"])

    return {
        "n": len(series.points),
        "domain": series.domain,
        "fields": fields,
        "diagnostics": diagnostics,
    }


__all__ = [
    "trend",
    "analyze_field",
    "first_difference",
    "second_difference",
    "CODE_TREND_TOO_SHORT",
    "CODE_TREND_SECOND_UNAVAILABLE",
    "CODE_TREND_SPARSE_FIELD",
    "CODE_TREND_NO_FIELDS",
]
