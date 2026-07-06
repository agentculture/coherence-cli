"""Offline contract tests for ``coherence.frames.inspect`` — reporting the frame
that produced a measurement JSON and whether its provenance is complete.

Per task t14's acceptance criteria: inspecting a measurement is a REPORT, never
an error. A v0.5.0-era measurement (no ``frame`` key at all — see
``coherence.meaning.score.score``'s ``{"meaning_score", "subdimensions",
"diagnostics"}`` shape) or an explicit null-frame must come back as a normal
result with a diagnostic naming the absence, so the CLI (task t16) can exit 0
on it rather than treating it as a crash.

Three states are distinguished:

* ``complete`` — a frame dict carrying all of embedding_model,
  embedding_endpoint, anchor_set, axis/axes, projection_method, score_type,
  each present and non-empty.
* ``partial`` — a frame dict present but missing one or more of those fields;
  the missing fields are named.
* ``absent`` — no ``frame`` key, ``frame: null``, or an explicit null-frame
  dict (:func:`coherence.schema.null_frame`'s
  ``{"available": False, "code", "reason"}`` shape) — whose machine-readable
  ``code``/``reason`` are surfaced when present.

Fully offline: no network, no embeddings call — this module only inspects
already-materialized measurement dicts.
"""

from __future__ import annotations

import pytest

from coherence.frames.inspect import (
    CODE_FRAME_ABSENT,
    CODE_FRAME_NULL_FRAME,
    CODE_FRAME_PARTIAL,
    STATUS_ABSENT,
    STATUS_COMPLETE,
    STATUS_PARTIAL,
    inspect_measurement,
)
from coherence.schema import null_frame

_COMPLETE_FRAME = {
    "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
    "embedding_endpoint": "http://localhost:8002/v1",
    "anchor_set": "meaning-v1",
    "projection_method": "contrastive_axis",
    "score_type": "model_relative_anchor_defined_projection",
    "axis": "valence",
}


def _measurement(frame, **extra):
    return {
        "domain": "meaning",
        "score_type": "model_relative_anchor_defined_projection",
        "scores": {"meaning_score": 0.5},
        "frame": frame,
        "diagnostics": [],
        **extra,
    }


# --- acceptance criterion 1: v0.5.0-era measurement (no frame key at all) ---


def test_inspect_v050_era_measurement_has_no_frame_key_reports_absent_never_raises() -> None:
    """coherence.meaning.score.score's exact pre-frame output shape."""
    measurement = {
        "meaning_score": 0.62,
        "subdimensions": {"agency": 0.4, "causality": 0.3},
        "diagnostics": [],
    }

    result = inspect_measurement(measurement)

    assert result["status"] == STATUS_ABSENT
    assert result["frame"] is None
    assert result["diagnostics"]
    assert any(d["code"] == CODE_FRAME_ABSENT for d in result["diagnostics"])


def test_inspect_v050_era_measurement_does_not_raise_at_all() -> None:
    measurement = {"meaning_score": 0.1, "subdimensions": {}, "diagnostics": []}
    # Must not raise anything -- a plain call is the whole assertion.
    inspect_measurement(measurement)


# --- explicit frame: null ---------------------------------------------------


def test_inspect_frame_null_reports_absent_with_diagnostic() -> None:
    measurement = _measurement(None)

    result = inspect_measurement(measurement)

    assert result["status"] == STATUS_ABSENT
    assert result["frame"] is None
    assert any(d["code"] == CODE_FRAME_ABSENT for d in result["diagnostics"])


# --- explicit null-frame dict (schema.null_frame) ---------------------------


def test_inspect_null_frame_dict_surfaces_machine_readable_reason_and_code() -> None:
    frame = null_frame("embedding endpoint was unreachable", code="frame_unavailable")
    measurement = _measurement(frame)

    result = inspect_measurement(measurement)

    assert result["status"] == STATUS_ABSENT
    assert result["reason"] == "embedding endpoint was unreachable"
    assert result["code"] == "frame_unavailable"
    assert any(d["code"] == CODE_FRAME_NULL_FRAME for d in result["diagnostics"])
    # the reason text should be traceable in the diagnostic message too
    assert any("unreachable" in d["message"] for d in result["diagnostics"])


def test_inspect_null_frame_dict_with_custom_code_is_preserved() -> None:
    frame = null_frame("no embed endpoint configured", code="no_endpoint_configured")
    measurement = _measurement(frame)

    result = inspect_measurement(measurement)

    assert result["code"] == "no_endpoint_configured"


# --- complete frame ----------------------------------------------------------


def test_inspect_complete_frame_reports_complete_with_no_missing_fields() -> None:
    measurement = _measurement(dict(_COMPLETE_FRAME))

    result = inspect_measurement(measurement)

    assert result["status"] == STATUS_COMPLETE
    assert result["missing_fields"] == []
    assert result["diagnostics"] == []
    assert result["frame"] == _COMPLETE_FRAME


def test_inspect_complete_frame_with_axes_list_instead_of_axis_is_complete() -> None:
    frame = dict(_COMPLETE_FRAME)
    del frame["axis"]
    frame["axes"] = ["valence", "arousal"]
    measurement = _measurement(frame)

    result = inspect_measurement(measurement)

    assert result["status"] == STATUS_COMPLETE
    assert result["missing_fields"] == []


# --- partial frame: fields missing, named -----------------------------------


@pytest.mark.parametrize(
    "missing_field",
    ["embedding_model", "embedding_endpoint", "anchor_set", "projection_method", "score_type"],
)
def test_inspect_partial_frame_names_each_missing_field(missing_field: str) -> None:
    frame = dict(_COMPLETE_FRAME)
    del frame[missing_field]
    measurement = _measurement(frame)

    result = inspect_measurement(measurement)

    assert result["status"] == STATUS_PARTIAL
    assert missing_field in result["missing_fields"]
    assert any(d["code"] == CODE_FRAME_PARTIAL for d in result["diagnostics"])
    assert any(missing_field in d["message"] for d in result["diagnostics"])


def test_inspect_partial_frame_with_empty_string_field_counts_as_missing() -> None:
    frame = dict(_COMPLETE_FRAME)
    frame["anchor_set"] = ""
    measurement = _measurement(frame)

    result = inspect_measurement(measurement)

    assert result["status"] == STATUS_PARTIAL
    assert "anchor_set" in result["missing_fields"]


def test_inspect_partial_frame_missing_both_axis_and_axes() -> None:
    frame = dict(_COMPLETE_FRAME)
    del frame["axis"]
    measurement = _measurement(frame)

    result = inspect_measurement(measurement)

    assert result["status"] == STATUS_PARTIAL
    assert "axis/axes" in result["missing_fields"]


def test_inspect_partial_frame_with_empty_axes_list_counts_as_missing() -> None:
    frame = dict(_COMPLETE_FRAME)
    del frame["axis"]
    frame["axes"] = []
    measurement = _measurement(frame)

    result = inspect_measurement(measurement)

    assert result["status"] == STATUS_PARTIAL
    assert "axis/axes" in result["missing_fields"]


def test_inspect_partial_frame_reports_multiple_missing_fields_together() -> None:
    frame = dict(_COMPLETE_FRAME)
    del frame["axis"]
    del frame["anchor_set"]
    measurement = _measurement(frame)

    result = inspect_measurement(measurement)

    assert result["status"] == STATUS_PARTIAL
    assert set(result["missing_fields"]) == {"axis/axes", "anchor_set"}


# --- malformed frame value: neither dict nor null ---------------------------


def test_inspect_non_dict_non_null_frame_is_treated_as_absent_not_a_crash() -> None:
    measurement = _measurement("not-a-frame")

    result = inspect_measurement(measurement)

    assert result["status"] == STATUS_ABSENT
    assert result["diagnostics"]


# --- never raises on any of the above ---------------------------------------


@pytest.mark.parametrize(
    "frame",
    [None, {}, dict(_COMPLETE_FRAME), null_frame("reason")],
)
def test_inspect_never_raises_for_any_valid_frame_shape(frame) -> None:
    inspect_measurement(_measurement(frame))
