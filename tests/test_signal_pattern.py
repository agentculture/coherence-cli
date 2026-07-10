"""Offline contract tests for ``coherence.signal.pattern`` — motif detection
over a loaded :class:`~coherence.signal.schema.Series`, per numeric field.

Each of the six motifs (``increasing``, ``decreasing``, ``plateau``,
``spike``, ``reversal``, ``stair_step``) is proven two ways: a synthetic
series built to exhibit it (the motif fires), and a counterexample series
built to lack it (the motif does not fire) — the pairing the task's
acceptance criteria call for. A separate group covers the "too short to
reason about direction" guard (n<3), the sparse-field gap diagnostic, and the
no-numeric-fields edge case.

Series are built directly from :class:`~coherence.signal.schema.SeriesPoint`
rather than through :func:`~coherence.signal.schema.load_series`, since these
tests exercise the pattern engine's own contract (it consumes a
:class:`Series`), not the loader's normalization rules (already covered by
``test_signal_schema.py``).
"""

from __future__ import annotations

import json

from coherence.signal.pattern import (
    CODE_FIELD_GAPS,
    CODE_INSUFFICIENT_POINTS,
    CODE_NO_FIELDS,
    MOTIF_DECREASING,
    MOTIF_INCREASING,
    MOTIF_PLATEAU,
    MOTIF_REVERSAL,
    MOTIF_SPIKE,
    MOTIF_STAIR_STEP,
    MOTIFS,
    detect_patterns,
)
from coherence.signal.schema import Series, SeriesPoint

# --- helpers ----------------------------------------------------------------


def _series(values: list[float], field: str = "m") -> Series:
    """Build a Series with one numeric field present at every point, in order."""
    return Series(
        points=[SeriesPoint(id=f"p{i}", index=i, values={field: v}) for i, v in enumerate(values)]
    )


def _series_multi(fields: dict[str, list[float]]) -> Series:
    """Build a Series with several numeric fields, all present at every point."""
    n = len(next(iter(fields.values())))
    points = []
    for i in range(n):
        values = {name: vals[i] for name, vals in fields.items()}
        points.append(SeriesPoint(id=f"p{i}", index=i, values=values))
    return Series(points=points)


def _series_sparse(n: int, present: dict[int, float], field: str = "m") -> Series:
    """Build an n-point Series where ``field`` only exists at the given indices."""
    points = []
    for i in range(n):
        values = {field: present[i]} if i in present else {}
        points.append(SeriesPoint(id=f"p{i}", index=i, values=values))
    return Series(points=points)


def _motifs_for(series: Series, field: str = "m") -> list[str]:
    result = detect_patterns(series)
    return result["fields"][field]["motifs"]


# --- acceptance 1: six motifs, synthetic detected + counterexample absent --


def test_increasing_detected_and_absent_on_counterexample() -> None:
    rising = _motifs_for(_series([1.0, 2.0, 3.0, 4.0, 5.0]))
    flat = _motifs_for(_series([5.0, 5.0, 5.0, 5.0, 5.0]))
    assert MOTIF_INCREASING in rising
    assert MOTIF_INCREASING not in flat


def test_decreasing_detected_and_absent_on_counterexample() -> None:
    falling = _motifs_for(_series([5.0, 4.0, 3.0, 2.0, 1.0]))
    rising = _motifs_for(_series([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert MOTIF_DECREASING in falling
    assert MOTIF_DECREASING not in rising


def test_plateau_detected_and_absent_on_counterexample() -> None:
    constant = _motifs_for(_series([3.0, 3.0, 3.0, 3.0, 3.0]))
    ramp = _motifs_for(_series([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert MOTIF_PLATEAU in constant
    assert MOTIF_PLATEAU not in ramp


def test_spike_detected_and_absent_on_counterexample() -> None:
    spiky = _motifs_for(_series([10.0, 10.0, 10.0, 100.0, 10.0, 10.0, 10.0]))
    smooth_ramp = _motifs_for(_series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]))
    assert MOTIF_SPIKE in spiky
    assert MOTIF_SPIKE not in smooth_ramp


def test_reversal_detected_and_absent_on_counterexample() -> None:
    up_then_down = _motifs_for(_series([1.0, 2.0, 3.0, 4.0, 3.0, 2.0, 1.0]))
    monotone = _motifs_for(_series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]))
    assert MOTIF_REVERSAL in up_then_down
    assert MOTIF_REVERSAL not in monotone


def test_stair_step_detected_and_absent_on_counterexample() -> None:
    staircase = _motifs_for(_series([1.0, 1.0, 3.0, 3.0, 5.0, 5.0, 7.0, 7.0]))
    smooth_ramp = _motifs_for(_series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]))
    assert MOTIF_STAIR_STEP in staircase
    assert MOTIF_STAIR_STEP not in smooth_ramp


def test_stair_step_also_detected_falling() -> None:
    """The mirror (fall-then-hold, repeated) is the same motif, not a new one."""
    descending_stairs = _motifs_for(_series([7.0, 7.0, 5.0, 5.0, 3.0, 3.0, 1.0, 1.0]))
    assert MOTIF_STAIR_STEP in descending_stairs


# --- acceptance 2: short series (n<3) get an explicit diagnostic, no motifs -


def test_single_point_series_yields_insufficient_points_diagnostic_no_motifs() -> None:
    result = detect_patterns(_series([1.0]))
    assert result["n"] == 1
    assert result["fields"] == {}
    codes = [d["code"] for d in result["diagnostics"]]
    assert CODE_INSUFFICIENT_POINTS in codes


def test_two_point_series_yields_insufficient_points_diagnostic_no_motifs() -> None:
    result = detect_patterns(_series([1.0, 2.0]))
    assert result["n"] == 2
    assert result["fields"] == {}
    codes = [d["code"] for d in result["diagnostics"]]
    assert CODE_INSUFFICIENT_POINTS in codes


def test_empty_series_yields_insufficient_points_diagnostic() -> None:
    result = detect_patterns(Series(points=[]))
    assert result["n"] == 0
    assert result["fields"] == {}
    codes = [d["code"] for d in result["diagnostics"]]
    assert CODE_INSUFFICIENT_POINTS in codes


# --- sparse fields: gaps get a diagnostic, present values still analyzed ---


def test_sparse_field_with_enough_present_values_gets_gap_diagnostic_and_motifs() -> None:
    # 5 points total, field present at 4 of them (index 2 missing); the
    # present values still form a clean increasing run.
    series = _series_sparse(5, {0: 1.0, 1: 2.0, 3: 4.0, 4: 5.0})
    result = detect_patterns(series)
    field = result["fields"]["m"]
    assert field["n_present"] == 4
    assert MOTIF_INCREASING in field["motifs"]
    codes = [d["code"] for d in result["diagnostics"]]
    assert CODE_FIELD_GAPS in codes


def test_field_with_too_few_present_values_gets_insufficient_points_not_motifs() -> None:
    # 5 points total, field present at only 2 of them.
    series = _series_sparse(5, {0: 1.0, 4: 5.0})
    result = detect_patterns(series)
    field = result["fields"]["m"]
    assert field["n_present"] == 2
    assert field["motifs"] == []
    assert field["insufficient_points"] is True
    codes = [d["code"] for d in result["diagnostics"]]
    assert CODE_INSUFFICIENT_POINTS in codes


def test_no_numeric_fields_at_all_gets_diagnostic() -> None:
    series = Series(
        points=[
            SeriesPoint(id="p0", index=0, values={}),
            SeriesPoint(id="p1", index=1, values={}),
            SeriesPoint(id="p2", index=2, values={}),
        ]
    )
    result = detect_patterns(series)
    assert result["fields"] == {}
    codes = [d["code"] for d in result["diagnostics"]]
    assert CODE_NO_FIELDS in codes


# --- multiple fields are analyzed independently ----------------------------


def test_multiple_fields_analyzed_independently() -> None:
    series = _series_multi(
        {
            "up": [1.0, 2.0, 3.0, 4.0, 5.0],
            "down": [5.0, 4.0, 3.0, 2.0, 1.0],
        }
    )
    result = detect_patterns(series)
    assert MOTIF_INCREASING in result["fields"]["up"]["motifs"]
    assert MOTIF_DECREASING not in result["fields"]["up"]["motifs"]
    assert MOTIF_DECREASING in result["fields"]["down"]["motifs"]
    assert MOTIF_INCREASING not in result["fields"]["down"]["motifs"]


# --- general contract: MOTIFS registry + JSON-serializable result ----------


def test_motifs_registry_lists_all_six_in_stable_order() -> None:
    assert list(MOTIFS) == [
        MOTIF_INCREASING,
        MOTIF_DECREASING,
        MOTIF_PLATEAU,
        MOTIF_SPIKE,
        MOTIF_REVERSAL,
        MOTIF_STAIR_STEP,
    ]


def test_result_is_json_serializable() -> None:
    result = detect_patterns(_series([1.0, 2.0, 3.0, 4.0, 5.0]))
    json.dumps(result)  # must not raise
