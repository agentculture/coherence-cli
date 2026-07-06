"""Offline contract tests for ``coherence.frames.compat`` — the mixed-frame
guard, and its wiring into :func:`coherence.signal.schema.load_series`.

Per task t14's acceptance criteria, a series whose per-point frames disagree
must never become a silent number downstream: :func:`check_series_frames`
walks a loaded :class:`~coherence.signal.schema.Series`'s points and appends a
visible warning diagnostic whenever they disagree, and
:func:`coherence.signal.schema.load_series` calls it automatically so the
guard fires at load time, not only when a caller remembers to invoke it by
hand.

Three rules, all exercised both directly against :func:`check_series_frames`
and end-to-end through :func:`load_series` (the acceptance-criterion path):

* all points' frames absent -> NOT mixed, no warning at all (missing
  provenance is ``frames inspect``'s job, not this guard's).
* some points framed, some not -> a ``partially_framed`` warning.
* two or more distinct non-null frame identities among the framed points -> a
  ``mixed_frames`` warning.

"Identity" here means the same four gauge fields :mod:`coherence.frames.diff`
uses to decide comparability (``embedding_model``, ``embedding_endpoint``,
``anchor_set``, ``projection_method``) — not ``axis``/``axes``/``score_type``,
which :mod:`coherence.frames.diff` treats as a softer, non-blocking
difference. This keeps the two engines' notion of "same frame" consistent.

Fully offline: no network, no embeddings call.
"""

from __future__ import annotations

from coherence.frames.compat import CODE_MIXED_FRAMES, CODE_PARTIALLY_FRAMED, check_series_frames
from coherence.signal.schema import Series, SeriesPoint, load_series

_FRAME_A = {
    "embedding_model": "model-a",
    "embedding_endpoint": "http://a:8002/v1",
    "anchor_set": "meaning-v1",
    "projection_method": "contrastive_axis",
    "score_type": "model_relative_anchor_defined_projection",
    "axis": "valence",
}

_FRAME_B = {
    "embedding_model": "model-b",
    "embedding_endpoint": "http://b:8002/v1",
    "anchor_set": "meaning-v2",
    "projection_method": "contrastive_axis",
    "score_type": "model_relative_anchor_defined_projection",
    "axis": "valence",
}


def _series(frames: list[dict | None]) -> Series:
    points = [
        SeriesPoint(id=f"p{i}", index=i, values={"meaning_score": 0.5}, frame=frame)
        for i, frame in enumerate(frames)
    ]
    return Series(points=points)


def _raw_series(frames: list) -> dict:
    points = []
    for i, frame in enumerate(frames):
        point = {"id": f"p{i}", "index": i, "values": {"meaning_score": 0.5}}
        if frame is not ...:
            point["frame"] = frame
        points.append(point)
    return {"points": points}


# --- direct: check_series_frames --------------------------------------------


def test_all_absent_frames_is_not_mixed_and_emits_nothing() -> None:
    series = _series([None, None, None])

    diagnostics = check_series_frames(series)

    assert diagnostics == []


def test_no_points_at_all_emits_nothing() -> None:
    series = _series([])

    assert check_series_frames(series) == []


def test_single_point_emits_nothing() -> None:
    series = _series([dict(_FRAME_A)])

    assert check_series_frames(series) == []


def test_identical_frames_across_points_is_not_mixed() -> None:
    series = _series([dict(_FRAME_A), dict(_FRAME_A), dict(_FRAME_A)])

    assert check_series_frames(series) == []


def test_some_present_some_absent_emits_partially_framed_warning() -> None:
    series = _series([dict(_FRAME_A), None])

    diagnostics = check_series_frames(series)

    assert any(d["code"] == CODE_PARTIALLY_FRAMED for d in diagnostics)
    assert not any(d["code"] == CODE_MIXED_FRAMES for d in diagnostics)


def test_two_distinct_identities_emits_mixed_frames_warning() -> None:
    series = _series([dict(_FRAME_A), dict(_FRAME_B)])

    diagnostics = check_series_frames(series)

    assert any(d["code"] == CODE_MIXED_FRAMES for d in diagnostics)


def test_mixed_and_partially_framed_can_both_fire_together() -> None:
    series = _series([dict(_FRAME_A), dict(_FRAME_B), None])

    diagnostics = check_series_frames(series)
    codes = {d["code"] for d in diagnostics}

    assert CODE_MIXED_FRAMES in codes
    assert CODE_PARTIALLY_FRAMED in codes


def test_axis_only_difference_does_not_trigger_mixed_frames() -> None:
    """Axis differences alone are not a gauge mismatch (matches diff.py's
    documented "soft difference" treatment of axis/axes/score_type)."""
    frame_a = dict(_FRAME_A)
    frame_b = dict(_FRAME_A)
    frame_b["axis"] = "arousal"
    series = _series([frame_a, frame_b])

    diagnostics = check_series_frames(series)

    assert not any(d["code"] == CODE_MIXED_FRAMES for d in diagnostics)


def test_null_frame_dicts_count_as_absent_not_a_distinct_identity() -> None:
    from coherence.schema import null_frame

    series = _series([dict(_FRAME_A), null_frame("unavailable")])

    diagnostics = check_series_frames(series)

    assert any(d["code"] == CODE_PARTIALLY_FRAMED for d in diagnostics)
    assert not any(d["code"] == CODE_MIXED_FRAMES for d in diagnostics)


# --- acceptance criterion 3: wired into load_series -------------------------


def test_load_series_surfaces_mixed_frame_warning_on_series_diagnostics() -> None:
    raw = _raw_series([dict(_FRAME_A), dict(_FRAME_B)])

    series = load_series(raw)

    assert any(d["code"] == CODE_MIXED_FRAMES for d in series.diagnostics)


def test_load_series_surfaces_partially_framed_warning_on_series_diagnostics() -> None:
    raw = _raw_series([dict(_FRAME_A), None])

    series = load_series(raw)

    assert any(d["code"] == CODE_PARTIALLY_FRAMED for d in series.diagnostics)


def test_load_series_emits_no_frame_warning_when_all_points_are_unframed() -> None:
    raw = _raw_series([..., ...])  # neither point carries a 'frame' key at all

    series = load_series(raw)

    codes = {d["code"] for d in series.diagnostics}
    assert CODE_MIXED_FRAMES not in codes
    assert CODE_PARTIALLY_FRAMED not in codes


def test_load_series_never_silently_drops_the_mixed_frame_signal() -> None:
    """A mixed-frame series must never come back with an EMPTY diagnostics
    list -- that would be exactly the silent-number failure mode this guard
    exists to prevent."""
    raw = _raw_series([dict(_FRAME_A), dict(_FRAME_B), dict(_FRAME_A)])

    series = load_series(raw)

    assert series.diagnostics != []
