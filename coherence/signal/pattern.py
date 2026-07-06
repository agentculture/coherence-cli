"""coherence.signal.pattern — motif detection over a loaded series, per field.

This is the shape-recognition sibling of :mod:`coherence.signal.trend`: where
``trend`` reports raw f'/f'' derivatives, ``pattern`` names the qualitative
shape those derivatives trace out. It consumes a normalized
:class:`~coherence.signal.schema.Series` (never a raw dict — call
:func:`coherence.signal.schema.load_series` first) and, for every numeric
field the series carries, reports which of six motifs the field's present
values exhibit:

* ``increasing`` / ``decreasing`` — an overall monotone direction, allowing a
  small noise tolerance.
* ``plateau`` — a sustained run of near-constant values.
* ``spike`` — a single point far from its neighbors that then returns to
  their level (as opposed to a lasting direction change).
* ``reversal`` — the direction flips exactly once: a rise then a fall, or a
  fall then a rise, each leg substantial enough to be a real turn rather than
  a single-point spike.
* ``stair_step`` — a repeated rise-then-hold (or fall-then-hold) staircase:
  at least two "step" runs separated by at least one "hold" run.

Motifs are independent per-field checks, not a mutually exclusive
classification — a field can exhibit more than one (e.g. a staircase that
nets out as an overall ``increasing`` run too). Each rule is documented and
gated by a module-level threshold constant (see "Thresholds" below); none of
it is learned or tuned against data, so results are fully deterministic and
reproducible run to run.

Sparse fields
-------------
A series field need not appear on every point (see
:mod:`coherence.signal.schema`: ``values`` is an open, per-point map). This
engine analyzes each field's *present* values only, in series order, treating
gaps as simply absent rather than interpolating a value for them — the same
"never fabricate a reading" stance as the schema loader. A field missing from
some (but not all) points earns a :data:`CODE_FIELD_GAPS` diagnostic naming
how many points it was missing from; the present values are still analyzed
normally.

Insufficient points
--------------------
Two points give exactly one step — not enough to distinguish a real trend
from noise — so motif detection needs at least :data:`_MIN_POINTS` (3) values
to run at all:

* If the *whole series* has fewer than 3 points, :func:`detect_patterns`
  returns immediately with an empty ``fields`` map and a
  :data:`CODE_INSUFFICIENT_POINTS` diagnostic — no motifs are computed for
  any field.
* If an individual field's *present* value count falls below 3 (because of
  gaps) while the series itself is long enough, that field alone gets an
  ``insufficient_points`` entry (empty ``motifs`` list, its own
  :data:`CODE_INSUFFICIENT_POINTS` diagnostic) while other, better-populated
  fields are still analyzed.

Output shape
------------
:func:`detect_patterns` returns a plain, JSON-serializable ``dict``::

    {
      "n": <int>,                     # total points in the series
      "fields": {
        "<field name>": {
          "n_present": <int>,          # how many points carry this field
          "motifs": ["increasing", ...],   # detected motif names (subset of MOTIFS)
          "insufficient_points": <bool>,   # True when n_present < 3 (motifs == [])
        },
        ...
      },
      "diagnostics": [{"code": <str>, "message": <str>}, ...]
    }

When the series has fewer than 3 points, or has no numeric fields at all,
``fields`` is ``{}`` and ``diagnostics`` names why.
"""

from __future__ import annotations

from typing import Callable

from coherence.signal.schema import Series

# --- machine-readable diagnostic codes --------------------------------------
CODE_INSUFFICIENT_POINTS = "pattern_insufficient_points"
CODE_FIELD_GAPS = "pattern_field_gaps"
CODE_NO_FIELDS = "pattern_no_fields"

# --- motif names, in the stable emission/registry order ---------------------
MOTIF_INCREASING = "increasing"
MOTIF_DECREASING = "decreasing"
MOTIF_PLATEAU = "plateau"
MOTIF_SPIKE = "spike"
MOTIF_REVERSAL = "reversal"
MOTIF_STAIR_STEP = "stair_step"

# --- thresholds --------------------------------------------------------------
#
# Every threshold below is a module constant precisely so it can be read,
# reasoned about, and (if ever needed) tuned in one place, each with the
# rationale that justifies its value.

# A series needs at least this many points to say anything about direction:
# two points give exactly one step (nothing to compare it against), three
# give at least two steps — enough to tell "noise" from "trend".
_MIN_POINTS = 3

# A step's size is judged against the field's OWN observed range, so the same
# rule works unchanged for a 0-1 bounded score and an unbounded counter alike.
# 5% of the range is treated as measurement noise (not a real move); the
# absolute floor keeps a perfectly constant field (range == 0) from
# collapsing the tolerance to exactly zero, which would make any nonzero
# floating-point wobble "significant". This also sidesteps ever comparing a
# float to `0.0` directly (a SonarCloud rule): every comparison below is
# against `tol`, never a bare zero.
_REL_TOL = 0.05
_ABS_TOL = 1e-9

# plateau: a "sustained" run needs at least this many CONSECUTIVE points
# within tolerance of one another — i.e. at least (_PLATEAU_MIN_RUN - 1)
# consecutive near-zero diffs.
_PLATEAU_MIN_RUN = 3

# spike: an interior point counts as "far" when it deviates from the AVERAGE
# of its two immediate neighbors by at least this fraction of the field's
# range, and it counts as "returns" when those same two neighbors agree with
# EACH OTHER within this (smaller) fraction of the range — i.e. the point is
# a one-off excursion away from an otherwise-steady baseline, not a step in a
# lasting move (which a reversal or stair_step would instead capture).
_SPIKE_MIN_DEVIATION_REL = 0.5
_SPIKE_NEIGHBOR_AGREEMENT_REL = 0.2

# reversal: the turning point (peak or trough) must be strictly interior,
# with at least this many points on EACH side of it. This is what separates a
# reversal (a real, multi-step turn) from a spike (a single elevated/dipped
# point that snaps back): a spike's "turn" has only one point on each side.
_REVERSAL_MIN_SEGMENT_POINTS = 2

# stair_step: a staircase needs at least this many "rise" (or "fall") runs,
# each separated by a "hold" run, to be more than a single ramp with a pause.
_STAIR_MIN_RUNS = 2


# --- shared numeric helpers --------------------------------------------------


def _value_range(values: list[float]) -> float:
    """Return ``max - min`` over ``values`` (``values`` must be non-empty)."""
    return max(values) - min(values)


def _tolerance(values: list[float]) -> float:
    """Return the noise tolerance for one field: 5% of its observed range.

    Floored at :data:`_ABS_TOL` so a constant field (range == 0) still gets a
    tiny positive tolerance rather than zero.
    """
    return max(_REL_TOL * _value_range(values), _ABS_TOL)


def _diffs(values: list[float]) -> list[float]:
    """Return the per-step difference ``[values[i+1] - values[i] for i]``."""
    return [values[i + 1] - values[i] for i in range(len(values) - 1)]


def _classify(diffs: list[float], tol: float) -> list[str]:
    """Label each diff ``"up"`` / ``"down"`` / ``"flat"`` against ``tol``."""
    return ["up" if d > tol else "down" if d < -tol else "flat" for d in diffs]


def _runs(labels: list[str]) -> list[str]:
    """Collapse consecutive identical labels, e.g. ``[up,up,flat,flat,up] -> [up,flat,up]``."""
    collapsed: list[str] = []
    for label in labels:
        if not collapsed or collapsed[-1] != label:
            collapsed.append(label)
    return collapsed


# --- motif detectors: each takes the present-value list, returns bool -------


def _is_increasing(values: list[float]) -> bool:
    """Overall monotone increase, allowing steps within tolerance to dip.

    Fires when no step decreases by more than ``tol`` (a genuine decrease
    anywhere breaks it) AND the net change end-to-end exceeds ``tol`` (so a
    flat/constant field, which has no decrease either, is not reported as
    "increasing").
    """
    diffs = _diffs(values)
    if not diffs:
        return False
    tol = _tolerance(values)
    if any(d < -tol for d in diffs):
        return False
    return (values[-1] - values[0]) > tol


def _is_decreasing(values: list[float]) -> bool:
    """Mirror of :func:`_is_increasing`: overall monotone decrease with tolerance."""
    diffs = _diffs(values)
    if not diffs:
        return False
    tol = _tolerance(values)
    if any(d > tol for d in diffs):
        return False
    return (values[0] - values[-1]) > tol


def _is_plateau(values: list[float]) -> bool:
    """A sustained near-constant run: >= (_PLATEAU_MIN_RUN - 1) consecutive small diffs."""
    diffs = _diffs(values)
    if len(diffs) < _PLATEAU_MIN_RUN - 1:
        return False
    tol = _tolerance(values)
    run = 0
    for d in diffs:
        if abs(d) <= tol:
            run += 1
            if run >= _PLATEAU_MIN_RUN - 1:
                return True
        else:
            run = 0
    return False


def _is_spike(values: list[float]) -> bool:
    """A single interior point far from its neighbors' average, which itself returns.

    See :data:`_SPIKE_MIN_DEVIATION_REL` / :data:`_SPIKE_NEIGHBOR_AGREEMENT_REL`
    for the exact "far" and "returns" thresholds.
    """
    n = len(values)
    if n < 3:
        return False
    rng = _value_range(values)
    if rng <= _ABS_TOL:
        return False
    for i in range(1, n - 1):
        neighbor_avg = (values[i - 1] + values[i + 1]) / 2.0
        deviation = abs(values[i] - neighbor_avg)
        neighbor_gap = abs(values[i - 1] - values[i + 1])
        far_enough = deviation >= _SPIKE_MIN_DEVIATION_REL * rng
        neighbors_agree = neighbor_gap <= _SPIKE_NEIGHBOR_AGREEMENT_REL * rng
        if far_enough and neighbors_agree:
            return True
    return False


def _has_peak_reversal(values: list[float], tol: float) -> bool:
    """Rise then fall: one interior maximum with a monotone leg on each side."""
    n = len(values)
    peak = max(range(n), key=lambda i: values[i])
    if peak < _REVERSAL_MIN_SEGMENT_POINTS or (n - 1 - peak) < _REVERSAL_MIN_SEGMENT_POINTS:
        return False
    rising = all(d >= -tol for d in _diffs(values[: peak + 1]))
    falling = all(d <= tol for d in _diffs(values[peak:]))
    rise_span = values[peak] - values[0]
    fall_span = values[peak] - values[-1]
    return rising and falling and rise_span > tol and fall_span > tol


def _has_trough_reversal(values: list[float], tol: float) -> bool:
    """Fall then rise: one interior minimum with a monotone leg on each side."""
    n = len(values)
    trough = min(range(n), key=lambda i: values[i])
    if trough < _REVERSAL_MIN_SEGMENT_POINTS or (n - 1 - trough) < _REVERSAL_MIN_SEGMENT_POINTS:
        return False
    falling = all(d <= tol for d in _diffs(values[: trough + 1]))
    rising = all(d >= -tol for d in _diffs(values[trough:]))
    fall_span = values[0] - values[trough]
    rise_span = values[-1] - values[trough]
    return falling and rising and fall_span > tol and rise_span > tol


def _is_reversal(values: list[float]) -> bool:
    """Direction flips exactly once: rise-then-fall (peak) or fall-then-rise (trough).

    Requires >= :data:`_REVERSAL_MIN_SEGMENT_POINTS` points on each side of the
    turn, which is what distinguishes a reversal from a :func:`_is_spike`
    (a single-point excursion has only one point on each side of its "turn").
    """
    n = len(values)
    if n < 2 * _REVERSAL_MIN_SEGMENT_POINTS + 1:
        return False
    tol = _tolerance(values)
    return _has_peak_reversal(values, tol) or _has_trough_reversal(values, tol)


def _is_stair_step(values: list[float]) -> bool:
    """A repeated rise-then-hold (or fall-then-hold) staircase.

    Classifies each step as up/down/flat, collapses consecutive identical
    labels into runs, and requires >= :data:`_STAIR_MIN_RUNS` "up" runs with
    zero "down" runs (or the mirror for "down"). Because collapsing never
    leaves two identical labels adjacent, >= 2 "up" runs with no "down" runs
    necessarily have a "flat" run between them — a rise/hold/rise staircase,
    not one long ramp (which collapses to a single "up" run).
    """
    diffs = _diffs(values)
    if len(diffs) < 2 * _STAIR_MIN_RUNS - 1:
        return False
    tol = _tolerance(values)
    runs = _runs(_classify(diffs, tol))
    ups = runs.count("up")
    downs = runs.count("down")
    if ups >= _STAIR_MIN_RUNS and downs == 0:
        return True
    return downs >= _STAIR_MIN_RUNS and ups == 0


# Registry, in the stable emission order named in the module docstring.
_MOTIF_DETECTORS: tuple[tuple[str, Callable[[list[float]], bool]], ...] = (
    (MOTIF_INCREASING, _is_increasing),
    (MOTIF_DECREASING, _is_decreasing),
    (MOTIF_PLATEAU, _is_plateau),
    (MOTIF_SPIKE, _is_spike),
    (MOTIF_REVERSAL, _is_reversal),
    (MOTIF_STAIR_STEP, _is_stair_step),
)

MOTIFS: tuple[str, ...] = tuple(name for name, _ in _MOTIF_DETECTORS)


def _diag(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _present_values(series: Series, field: str) -> list[float]:
    """Return ``field``'s values in series order, skipping points where absent."""
    return [point.values[field] for point in series.points if field in point.values]


def _field_result(series: Series, field: str, diagnostics: list[dict[str, str]]) -> dict:
    """Analyze one field: gap diagnostic (if sparse) + motifs (if enough present values)."""
    n_total = len(series.points)
    values = _present_values(series, field)
    n_present = len(values)
    if n_present < n_total:
        diagnostics.append(
            _diag(
                CODE_FIELD_GAPS,
                f"field {field!r}: present at {n_present}/{n_total} points; motifs are "
                "computed over the present values only (gaps are skipped, never "
                "interpolated)",
            )
        )
    if n_present < _MIN_POINTS:
        diagnostics.append(
            _diag(
                CODE_INSUFFICIENT_POINTS,
                f"field {field!r}: only {n_present} present value(s); pattern detection "
                f"needs at least {_MIN_POINTS} to reason about direction, so no motifs "
                "were computed for this field",
            )
        )
        return {"n_present": n_present, "motifs": [], "insufficient_points": True}
    motifs = [name for name, detector in _MOTIF_DETECTORS if detector(values)]
    return {"n_present": n_present, "motifs": motifs, "insufficient_points": False}


def detect_patterns(series: Series) -> dict:
    """Detect motifs in every numeric field of ``series``.

    Args:
        series: A normalized :class:`~coherence.signal.schema.Series` (load
            raw input through :func:`coherence.signal.schema.load_series`
            first).

    Returns:
        A JSON-serializable ``dict`` — see the module docstring for the exact
        shape. When the series has fewer than :data:`_MIN_POINTS` points, or
        carries no numeric fields at all, ``fields`` is ``{}`` and
        ``diagnostics`` names why; no motifs are computed in either case.
    """
    n = len(series.points)
    diagnostics: list[dict[str, str]] = []

    if n < _MIN_POINTS:
        diagnostics.append(
            _diag(
                CODE_INSUFFICIENT_POINTS,
                f"series has {n} point(s); pattern detection needs at least "
                f"{_MIN_POINTS} to reason about direction, so no motifs were computed",
            )
        )
        return {"n": n, "fields": {}, "diagnostics": diagnostics}

    field_names = sorted(series.field_names())
    if not field_names:
        diagnostics.append(
            _diag(CODE_NO_FIELDS, "series has no numeric fields on any point; nothing to analyze")
        )
        return {"n": n, "fields": {}, "diagnostics": diagnostics}

    fields: dict[str, dict] = {}
    for name in field_names:
        fields[name] = _field_result(series, name, diagnostics)

    return {"n": n, "fields": fields, "diagnostics": diagnostics}


__all__ = [
    "detect_patterns",
    "MOTIFS",
    "MOTIF_INCREASING",
    "MOTIF_DECREASING",
    "MOTIF_PLATEAU",
    "MOTIF_SPIKE",
    "MOTIF_REVERSAL",
    "MOTIF_STAIR_STEP",
    "CODE_INSUFFICIENT_POINTS",
    "CODE_FIELD_GAPS",
    "CODE_NO_FIELDS",
]
