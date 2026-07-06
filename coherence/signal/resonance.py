"""coherence.signal.resonance — pairwise SIGNED alignment between series fields.

This is the second engine over the shared :mod:`coherence.signal.schema`
series shape (see ``docs/signal-series.md``). It answers one question for
every pair of numeric fields in a series: *do these two streams move
together, or against each other?* The answer is ONE signed number per pair —
Pearson correlation over the points where both fields are present — and the
sign IS the meaning:

* **positive** alignment → the fields reinforce each other → ``"resonance"``
* **negative** alignment → the fields conflict → ``"interference"``
* a small band around zero → ``"neutral"`` (see :data:`NEUTRAL_BAND`)

This is a deliberate spec decision, not an oversight: resonance and
interference are the SAME computation read by its sign, not two separate
engines. There is exactly one code path (:func:`_alignment`) computing the
metric; :func:`_relation` only *labels* the sign of that one number. A test
suite that exercises "resonance" and "interference" as if they were different
algorithms is testing the wrong thing — see ``docs/signal-series.md``'s note
that "standalone interference families" are explicitly *not* built here.

Never a fabricated correlation
-------------------------------
A Pearson correlation is only meaningful when both fields actually vary and
there are enough shared observations to estimate it. Two guards keep bogus
numbers out of the output entirely (excluded with a diagnostic, never
computed as ``NaN``):

* **Too few common points** — fewer than :data:`MIN_COMMON_POINTS` points
  where *both* fields of the pair are present (``CODE_TOO_FEW_COMMON_POINTS``).
* **Constant field(s)** — zero variance over the common points makes the
  correlation undefined (division by a zero standard deviation)
  (``CODE_CONSTANT_FIELD``).

A third guard (``CODE_NON_FINITE_CORRELATION``) is defensive: even if a
caller hands the engine a :class:`~coherence.signal.schema.Series` built
outside the normal loader (bypassing its validation) and a value happens to
be non-finite (e.g. ``float('nan')``, which *is* a legitimate Python
``float``), the resulting non-finite correlation is still excluded rather
than surfaced.

Fields are read from :meth:`~coherence.signal.schema.Series.field_names` —
the signal layer never enumerates field names itself, so any caller-defined
value name pairs up with any other automatically.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np

from coherence.signal.schema import Series

# --- machine-readable diagnostic codes -------------------------------------
CODE_TOO_FEW_COMMON_POINTS = "resonance_too_few_common_points"
CODE_CONSTANT_FIELD = "resonance_constant_field"
CODE_NON_FINITE_CORRELATION = "resonance_non_finite_correlation"

# --- relation labels --------------------------------------------------------
# Derived from the SIGN of the single ``alignment`` metric — never computed
# independently. See the module docstring: this is the whole spec decision.
RELATION_RESONANCE = "resonance"
RELATION_INTERFERENCE = "interference"
RELATION_NEUTRAL = "neutral"

# A pair needs at least this many points where BOTH fields are present before
# a Pearson correlation means anything more than a coincidence of few points.
# Below 3 points a correlation is either undefined (n=1) or trivially +-1
# (n=2, two points always lie on a line), so both are excluded rather than
# reported as a real signal.
MIN_COMMON_POINTS = 3

# Alignment values with absolute value at or below this band are reported as
# "neutral" rather than resonance/interference — this guards against reading
# meaning into noise clustered around zero. A module constant so callers (and
# a later CLI layer) can reference the exact threshold used here.
NEUTRAL_BAND = 0.1

# A standard deviation at or below this is treated as "zero variance" (a
# constant field) — a small epsilon rather than an exact ``== 0.0`` float
# comparison, which is fragile against floating-point noise.
_STD_EPS = 1e-12


def _diag(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _relation(alignment: float) -> str:
    """Label the sign of ``alignment`` — the ONLY thing this function does.

    This is the entire "resonance vs. interference" decision: it is a pure
    function of the sign of the one alignment metric, never an independent
    computation.
    """
    if alignment > NEUTRAL_BAND:
        return RELATION_RESONANCE
    if alignment < -NEUTRAL_BAND:
        return RELATION_INTERFERENCE
    return RELATION_NEUTRAL


def _common_values(series: Series, field_a: str, field_b: str) -> tuple[list[float], list[float]]:
    """Return the ``(xs, ys)`` values of ``field_a``/``field_b`` at points where
    both are present, in series order.
    """
    xs: list[float] = []
    ys: list[float] = []
    for point in series.points:
        if field_a in point.values and field_b in point.values:
            xs.append(point.values[field_a])
            ys.append(point.values[field_b])
    return xs, ys


def _constant_field_names(
    xs: list[float], ys: list[float], field_a: str, field_b: str
) -> list[str]:
    """Return the names (from ``field_a``/``field_b``) whose values are constant."""
    names: list[str] = []
    if float(np.std(np.asarray(xs, dtype=np.float64))) <= _STD_EPS:
        names.append(field_a)
    if float(np.std(np.asarray(ys, dtype=np.float64))) <= _STD_EPS:
        names.append(field_b)
    return names


def _alignment(xs: list[float], ys: list[float]) -> float | None:
    """Return the Pearson correlation of ``xs``/``ys``, or ``None`` if non-finite.

    Callers are expected to have already excluded the too-few-points and
    constant-field cases; this is the final defensive guard so a non-finite
    result (e.g. from a NaN sneaked past the schema loader) is never returned.
    """
    x = np.asarray(xs, dtype=np.float64)
    y = np.asarray(ys, dtype=np.float64)
    corr = float(np.corrcoef(x, y)[0, 1])
    if not np.isfinite(corr):
        return None
    # Clamp tiny floating-point excursions outside [-1, 1].
    return max(-1.0, min(1.0, corr))


def resonance(series: Series) -> dict[str, Any]:
    """Compute pairwise SIGNED alignment between every pair of numeric fields.

    For every unordered pair of field names present anywhere in ``series``,
    correlate the two fields over the points where both are present. A pair
    is EXCLUDED (never given a fabricated or ``NaN`` value) when it has fewer
    than :data:`MIN_COMMON_POINTS` shared points, when either field is
    constant over those points, or — defensively — when the correlation is
    non-finite for any other reason; each exclusion appends one diagnostic.

    Args:
        series: The normalized :class:`~coherence.signal.schema.Series` to
            analyze. Field names are read from
            :meth:`~coherence.signal.schema.Series.field_names`; the engine
            never enumerates or assumes any particular name.

    Returns:
        A plain, JSON-serializable dict::

            {
              "pairs": [
                {"a": <field>, "b": <field>, "alignment": <float in [-1, 1]>,
                 "relation": "resonance"|"interference"|"neutral", "n": <int>},
                ...
              ],
              "diagnostics": [{"code": <str>, "message": <str>}, ...]
            }

        ``pairs`` is ordered by the sorted field-name pair (deterministic
        regardless of point-insertion order). ``alignment`` is the single
        signed metric; ``relation`` is derived purely from its sign (see
        :func:`_relation`) — never an independently computed value.
    """
    diagnostics: list[dict[str, str]] = []
    pairs: list[dict[str, Any]] = []

    field_names = sorted(series.field_names())
    for field_a, field_b in combinations(field_names, 2):
        xs, ys = _common_values(series, field_a, field_b)

        if len(xs) < MIN_COMMON_POINTS:
            diagnostics.append(
                _diag(
                    CODE_TOO_FEW_COMMON_POINTS,
                    f"{field_a!r}/{field_b!r}: only {len(xs)} common point(s), "
                    f"need at least {MIN_COMMON_POINTS}; pair excluded",
                )
            )
            continue

        constant_names = _constant_field_names(xs, ys, field_a, field_b)
        if constant_names:
            diagnostics.append(
                _diag(
                    CODE_CONSTANT_FIELD,
                    f"{field_a!r}/{field_b!r}: {', '.join(map(repr, constant_names))} "
                    f"constant (zero variance) over {len(xs)} common point(s); "
                    "correlation undefined, pair excluded",
                )
            )
            continue

        alignment = _alignment(xs, ys)
        if alignment is None:
            diagnostics.append(
                _diag(
                    CODE_NON_FINITE_CORRELATION,
                    f"{field_a!r}/{field_b!r}: correlation over {len(xs)} common "
                    "point(s) was non-finite; pair excluded",
                )
            )
            continue

        pairs.append(
            {
                "a": field_a,
                "b": field_b,
                "alignment": alignment,
                "relation": _relation(alignment),
                "n": len(xs),
            }
        )

    return {"pairs": pairs, "diagnostics": diagnostics}


__all__ = [
    "resonance",
    "CODE_TOO_FEW_COMMON_POINTS",
    "CODE_CONSTANT_FIELD",
    "CODE_NON_FINITE_CORRELATION",
    "RELATION_RESONANCE",
    "RELATION_INTERFERENCE",
    "RELATION_NEUTRAL",
    "MIN_COMMON_POINTS",
    "NEUTRAL_BAND",
]
