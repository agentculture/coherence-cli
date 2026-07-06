"""Offline contract tests for ``coherence.frames.diff`` — are two measurements
frame-COMPARABLE (same gauge)?

Per task t14's acceptance criteria: two measurements are only safely comparable
when they share the same *identity* — ``embedding_model``,
``embedding_endpoint``, ``anchor_set``, ``projection_method`` (the same
embedding model, endpoint, anchor set, and projection method: the actual
"gauge"). ``axis``/``axes`` and ``score_type`` differences are reported too
(the caller may still care that a different axis or falsifiability class was
measured) but — this module's documented call — do not by themselves flip
``comparable`` to ``False``: they are surfaced as ``soft_differences`` rather
than ``differing_fields``, since two measurements can share a gauge while
projecting a different axis through it.

Absent frames are handled explicitly, each with its own machine-readable code:
one side absent + the other present is not comparable (asymmetric provenance);
both sides absent is not comparable for a different reason ("no provenance to
compare" at all) — these are two distinct, documented failure codes, not one
generic "false".

Fully offline: no network, no embeddings call.
"""

from __future__ import annotations

import pytest

from coherence.frames.diff import (
    CODE_ASYMMETRIC_FRAME_PRESENCE,
    CODE_FRAME_IDENTITY_MISMATCH,
    CODE_FRAMES_COMPARABLE,
    CODE_NO_PROVENANCE_TO_COMPARE,
    diff_frames,
)
from coherence.schema import null_frame

_BASE_FRAME = {
    "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
    "embedding_endpoint": "http://localhost:8002/v1",
    "anchor_set": "meaning-v1",
    "projection_method": "contrastive_axis",
    "score_type": "model_relative_anchor_defined_projection",
    "axis": "valence",
}


def _frame(**overrides):
    frame = dict(_BASE_FRAME)
    frame.update(overrides)
    return frame


def _measurement(frame, **extra):
    return {
        "domain": "meaning",
        "score_type": "model_relative_anchor_defined_projection",
        "scores": {"meaning_score": 0.5},
        "frame": frame,
        "diagnostics": [],
        **extra,
    }


def _v050_measurement() -> dict:
    """A measurement with no ``frame`` key at all (pre-frame era)."""
    return {"meaning_score": 0.4, "subdimensions": {}, "diagnostics": []}


# --- same gauge --------------------------------------------------------------


def test_diff_identical_frames_are_comparable() -> None:
    a = _measurement(_frame())
    b = _measurement(_frame())

    result = diff_frames(a, b)

    assert result["comparable"] is True
    assert result["code"] == CODE_FRAMES_COMPARABLE
    assert result["differing_fields"] == {}


# --- acceptance criterion 2: differing embedding_model ----------------------


def test_diff_different_embedding_model_is_not_comparable_and_names_the_field() -> None:
    a = _measurement(_frame(embedding_model="model-a"))
    b = _measurement(_frame(embedding_model="model-b"))

    result = diff_frames(a, b)

    assert result["comparable"] is False
    assert result["code"] == CODE_FRAME_IDENTITY_MISMATCH
    assert "embedding_model" in result["differing_fields"]
    assert result["differing_fields"]["embedding_model"] == {"a": "model-a", "b": "model-b"}


@pytest.mark.parametrize(
    "field", ["embedding_model", "embedding_endpoint", "anchor_set", "projection_method"]
)
def test_diff_each_identity_field_difference_is_named_and_blocks_comparability(
    field: str,
) -> None:
    a = _measurement(_frame(**{field: "value-a"}))
    b = _measurement(_frame(**{field: "value-b"}))

    result = diff_frames(a, b)

    assert result["comparable"] is False
    assert field in result["differing_fields"]
    assert result["differing_fields"][field] == {"a": "value-a", "b": "value-b"}


def test_diff_multiple_identity_field_differences_are_all_named() -> None:
    a = _measurement(_frame(embedding_model="model-a", anchor_set="anchors-a"))
    b = _measurement(_frame(embedding_model="model-b", anchor_set="anchors-b"))

    result = diff_frames(a, b)

    assert result["comparable"] is False
    assert set(result["differing_fields"]) == {"embedding_model", "anchor_set"}


# --- axis/score_type differences: soft, non-blocking (documented call) -----


def test_diff_axis_difference_alone_is_still_comparable_but_reported() -> None:
    a = _measurement(_frame(axis="valence"))
    b = _measurement(_frame(axis="arousal"))

    result = diff_frames(a, b)

    assert result["comparable"] is True
    assert result["differing_fields"] == {}
    assert "axis" in result["soft_differences"]
    assert result["soft_differences"]["axis"] == {"a": "valence", "b": "arousal"}


def test_diff_score_type_difference_alone_is_still_comparable_but_reported() -> None:
    a = _measurement(_frame(score_type="type-a"))
    b = _measurement(_frame(score_type="type-b"))

    result = diff_frames(a, b)

    assert result["comparable"] is True
    assert "score_type" in result["soft_differences"]


def test_diff_axes_list_vs_axis_string_difference_is_soft() -> None:
    frame_a = _frame()
    frame_b = dict(_BASE_FRAME)
    del frame_b["axis"]
    frame_b["axes"] = ["valence", "arousal"]

    result = diff_frames(_measurement(frame_a), _measurement(frame_b))

    assert result["comparable"] is True
    assert "axis" in result["soft_differences"]


# --- absent frames: two distinct, documented codes --------------------------


def test_diff_both_absent_no_frame_key_is_not_comparable_with_its_own_code() -> None:
    a = _v050_measurement()
    b = _v050_measurement()

    result = diff_frames(a, b)

    assert result["comparable"] is False
    assert result["code"] == CODE_NO_PROVENANCE_TO_COMPARE


def test_diff_both_null_frame_is_not_comparable_with_no_provenance_code() -> None:
    a = _measurement(None)
    b = _measurement(null_frame("no endpoint"))

    result = diff_frames(a, b)

    assert result["comparable"] is False
    assert result["code"] == CODE_NO_PROVENANCE_TO_COMPARE


def test_diff_one_absent_one_present_is_not_comparable_with_asymmetric_code() -> None:
    a = _v050_measurement()
    b = _measurement(_frame())

    result = diff_frames(a, b)

    assert result["comparable"] is False
    assert result["code"] == CODE_ASYMMETRIC_FRAME_PRESENCE


def test_diff_present_then_absent_order_still_reports_asymmetric_code() -> None:
    a = _measurement(_frame())
    b = _measurement(None)

    result = diff_frames(a, b)

    assert result["comparable"] is False
    assert result["code"] == CODE_ASYMMETRIC_FRAME_PRESENCE


def test_diff_asymmetric_and_no_provenance_codes_are_distinct() -> None:
    assert CODE_ASYMMETRIC_FRAME_PRESENCE != CODE_NO_PROVENANCE_TO_COMPARE


# --- never raises -------------------------------------------------------------


def test_diff_never_raises_across_all_frame_shapes() -> None:
    shapes = [None, _frame(), null_frame("x"), "not-a-frame"]
    for a_frame in shapes:
        for b_frame in shapes:
            diff_frames(_measurement(a_frame), _measurement(b_frame))
