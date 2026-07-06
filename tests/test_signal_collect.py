"""Tests for coherence.signal.collect — building a series from N measurement JSONs.

The collect module is the glue that turns per-artifact measurements (from any
domain) into analyzable signals by extracting numeric values generically, shape-
driven not domain-driven.

Acceptance criteria (task t9):

1. Collect accepts meaning-shaped, quality-shaped (real output from
   coherence.quality.score.score_text), and investiture-shaped (hand-written
   full-envelope with domain="investiture") score JSONs in ONE call — envelope/
   shape-driven, no per-domain code — and emits a series that load_series
   validates cleanly.
2. Input ordering is preserved (indexes 0..n-1 match input order) and each
   point carries the source measurement's frame block (or explicit null-frame/None).
3. Zero numeric leaves in an input → RAISE the schema's error convention
   (SeriesError with .code) so the CLI can map it to exit 1 later.

Every test is fully OFFLINE and deterministic.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from coherence.schema import build_envelope, null_frame
from coherence.signal.collect import collect, collect_files
from coherence.signal.schema import SeriesError, load_series

# --- helpers: build test measurement data -----------------------------------


def _meaning_measurement(
    meaning_score: float = 0.75,
    subdimensions: dict | None = None,
    *,
    domain: str = "meaning",
    score_type: str = "model_relative_anchor_defined_projection",
    frame: dict | None = None,
    diagnostics: list | None = None,
) -> dict:
    """Build a meaning-shaped measurement (old format with additive envelope keys)."""
    if subdimensions is None:
        subdimensions = {
            "consequence": 0.7,
            "agency": 0.8,
            "causality": 0.65,
            "affordance": 0.9,
            "future_constraint": 0.6,
        }
    result = {
        "meaning_score": meaning_score,
        "subdimensions": subdimensions,
        "diagnostics": diagnostics or [],
        "domain": domain,
        "score_type": score_type,
        "frame": frame,
    }
    return result


def _quality_measurement(
    freshness: float = 0.8,
    provenance: float = 0.5,
    fidelity: float = 0.4,
    *,
    frame: dict | None = None,
) -> dict:
    """Build a quality-shaped measurement (full envelope with scores dict)."""
    return build_envelope(
        domain="quality",
        score_type="rule_based_heuristic",
        scores={
            "freshness": freshness,
            "freshness_confidence": 0.9,
            "provenance": provenance,
            "provenance_confidence": 0.7,
            "fidelity": fidelity,
            "fidelity_confidence": 0.6,
        },
        frame=frame
        or null_frame("rule_based_no_embedding_frame", code="rule_based_no_embedding_frame"),
        diagnostics=[],
    )


def _investiture_measurement(
    engagement: float = 0.85,
    authenticity: float = 0.72,
    *,
    frame: dict | None = None,
) -> dict:
    """Build an investiture-shaped measurement (full envelope, custom domain)."""
    return build_envelope(
        domain="investiture",
        score_type="model_relative_anchor_defined_projection",
        scores={
            "engagement": engagement,
            "authenticity": authenticity,
        },
        frame=frame,
        diagnostics=[],
    )


# --- acceptance 1: shape-driven collection, no per-domain branching --------


def test_collect_accepts_meaning_shaped_measurements() -> None:
    """Meaning-shaped measurements (old format) extract numeric values."""
    measurements = [
        _meaning_measurement(meaning_score=0.6, subdimensions={"consequence": 0.5}),
        _meaning_measurement(meaning_score=0.7, subdimensions={"consequence": 0.65}),
    ]
    series_dict = collect(measurements)

    # Must be loadable by load_series
    series = load_series(series_dict)
    assert series.domain == "meaning"
    assert len(series.points) == 2
    assert series.points[0].index == 0
    assert series.points[1].index == 1
    # Both meaning_score and subdimensions.consequence are extracted
    assert "meaning_score" in series.points[0].values
    assert "consequence" in series.points[0].values
    assert series.points[0].values["meaning_score"] == 0.6
    assert series.points[0].values["consequence"] == 0.5


def test_collect_accepts_quality_shaped_measurements() -> None:
    """Quality-shaped measurements (full envelope) extract from scores dict."""
    measurements = [
        _quality_measurement(freshness=0.8, provenance=0.5, fidelity=0.4),
        _quality_measurement(freshness=0.75, provenance=0.6, fidelity=0.45),
    ]
    series_dict = collect(measurements)

    series = load_series(series_dict)
    assert series.domain == "quality"
    assert len(series.points) == 2
    # All six numeric values from scores dict extracted
    assert "freshness" in series.points[0].values
    assert "freshness_confidence" in series.points[0].values
    assert "provenance" in series.points[0].values
    assert series.points[0].values["freshness"] == 0.8


def test_collect_accepts_investiture_shaped_measurements() -> None:
    """Investiture-shaped measurements (full envelope) extract from scores dict."""
    measurements = [
        _investiture_measurement(engagement=0.85, authenticity=0.72),
        _investiture_measurement(engagement=0.90, authenticity=0.75),
    ]
    series_dict = collect(measurements)

    series = load_series(series_dict)
    assert series.domain == "investiture"
    assert len(series.points) == 2
    assert "engagement" in series.points[0].values
    assert "authenticity" in series.points[0].values
    assert series.points[0].values["engagement"] == 0.85


def test_collect_shape_driven_not_domain_driven() -> None:
    """Collection works on shape, not domain name — same extraction path."""
    # A custom domain using full envelope shape
    custom_envelope = build_envelope(
        domain="custom_metric",
        score_type="test_heuristic",
        scores={"metric_a": 0.5, "metric_b": 0.6},
        frame=None,
        diagnostics=[],
    )
    series_dict = collect([custom_envelope])
    series = load_series(series_dict)
    assert series.domain == "custom_metric"
    assert series.points[0].values == {"metric_a": 0.5, "metric_b": 0.6}


# --- acceptance 2: ordering preserved, frames carried ----------------------


def test_collect_preserves_input_order_and_indexes() -> None:
    """Input order is preserved; index matches list position."""
    measurements = [
        _quality_measurement(freshness=0.1),
        _quality_measurement(freshness=0.2),
        _quality_measurement(freshness=0.3),
        _quality_measurement(freshness=0.4),
    ]
    series_dict = collect(measurements)
    series = load_series(series_dict)

    assert len(series.points) == 4
    for i, point in enumerate(series.points):
        assert point.index == i
        assert point.values["freshness"] == pytest.approx(0.1 + (i * 0.1))


def test_collect_carries_frame_from_measurement() -> None:
    """Per-point frame from measurement is carried to the series."""
    frame1 = {"embedding_model": "model_v1"}
    frame2 = {"embedding_model": "model_v2"}
    measurements = [
        _quality_measurement(frame=frame1),
        _quality_measurement(frame=frame2),
    ]
    series_dict = collect(measurements)
    series = load_series(series_dict)

    assert series.points[0].frame == frame1
    assert series.points[1].frame == frame2


def test_collect_carries_null_frame() -> None:
    """Explicit null frame is carried through (a null-frame dict is still a frame dict)."""
    # Note: null_frame() returns a dict, not None. A measurement with no frame
    # information still carries this dict to signal the absence.
    # This tests that frames from measurements (including null-frame dicts)
    # are carried through.
    frame_dict = null_frame("test_reason")
    measurements = [
        _quality_measurement(frame=frame_dict),
        _quality_measurement(frame=frame_dict),
    ]
    series_dict = collect(measurements)
    series = load_series(series_dict)

    assert series.points[0].frame == frame_dict
    assert series.points[1].frame == frame_dict


# --- acceptance 3: zero numeric leaves → error ----------------------------


def test_collect_raises_on_zero_numeric_values() -> None:
    """An input with no extractable numeric values raises SeriesError with code."""
    measurement_no_numerics = {
        "domain": "test",
        "score_type": "test",
        "scores": {},  # Empty scores dict
        "frame": None,
        "diagnostics": [],
    }
    with pytest.raises(SeriesError) as exc_info:
        collect([measurement_no_numerics])
    assert hasattr(exc_info.value, "code")
    assert exc_info.value.code == "collect_no_numeric_values"


def test_collect_raises_on_all_zero_numeric_inputs() -> None:
    """When ALL inputs have zero numeric values, raise error."""
    measurements = [
        {"domain": "test", "score_type": "test", "scores": {}, "frame": None, "diagnostics": []},
        {"domain": "test", "score_type": "test", "scores": {}, "frame": None, "diagnostics": []},
    ]
    with pytest.raises(SeriesError) as exc_info:
        collect(measurements)
    assert exc_info.value.code == "collect_no_numeric_values"


# --- ID handling -----------------------------------------------------------


def test_collect_uses_explicit_ids() -> None:
    """When ids are provided, they are used as point ids."""
    measurements = [
        _quality_measurement(),
        _quality_measurement(),
    ]
    series_dict = collect(measurements, ids=["artifact_v1", "artifact_v2"])
    series = load_series(series_dict)

    assert series.points[0].id == "artifact_v1"
    assert series.points[1].id == "artifact_v2"


def test_collect_synthesizes_ids_when_not_provided() -> None:
    """When ids are not provided, points are synthesized as point-<index>."""
    measurements = [_quality_measurement(), _quality_measurement()]
    series_dict = collect(measurements)
    series = load_series(series_dict)

    assert series.points[0].id == "point-0"
    assert series.points[1].id == "point-1"


def test_collect_ids_count_must_match_measurements() -> None:
    """IDs list length must match measurements length."""
    measurements = [_quality_measurement(), _quality_measurement()]
    with pytest.raises((ValueError, IndexError)):
        collect(measurements, ids=["only_one"])


# --- domain handling -------------------------------------------------------


def test_collect_domain_when_all_same() -> None:
    """When all measurements have the same domain, it is set on the series."""
    measurements = [
        _quality_measurement(),
        _quality_measurement(),
    ]
    series_dict = collect(measurements)
    assert series_dict["domain"] == "quality"


def test_collect_domain_null_when_mixed() -> None:
    """When measurements have different domains, series domain is null."""
    measurements = [
        _quality_measurement(),
        _investiture_measurement(),
    ]
    series_dict = collect(measurements)
    assert series_dict["domain"] is None


def test_collect_domain_null_when_missing() -> None:
    """When a measurement lacks a domain key, series domain becomes null."""
    measurements = [
        _quality_measurement(),
        {"scores": {"value": 0.5}, "frame": None, "diagnostics": []},  # No domain
    ]
    series_dict = collect(measurements)
    assert series_dict["domain"] is None


# --- file collection -------------------------------------------------------


def test_collect_files_loads_json_files() -> None:
    """collect_files reads JSON files and collects them."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        file1 = tmpdir_path / "measurement_1.json"
        file2 = tmpdir_path / "measurement_2.json"

        file1.write_text(json.dumps(_quality_measurement(freshness=0.8)))
        file2.write_text(json.dumps(_quality_measurement(freshness=0.75)))

        series_dict = collect_files([str(file1), str(file2)])
        series = load_series(series_dict)

        assert len(series.points) == 2
        assert series.points[0].values["freshness"] == 0.8
        assert series.points[1].values["freshness"] == 0.75


def test_collect_files_uses_filenames_as_ids() -> None:
    """collect_files uses filenames (without path) as point ids."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        file1 = tmpdir_path / "v1.json"
        file2 = tmpdir_path / "v2.json"

        file1.write_text(json.dumps(_quality_measurement()))
        file2.write_text(json.dumps(_quality_measurement()))

        series_dict = collect_files([str(file1), str(file2)])
        series = load_series(series_dict)

        assert series.points[0].id == "v1.json"
        assert series.points[1].id == "v2.json"


def test_collect_files_preserves_file_order() -> None:
    """Files are collected in order provided."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        files = [tmpdir_path / f"f{i}.json" for i in range(3)]
        for i, f in enumerate(files):
            f.write_text(json.dumps(_quality_measurement(freshness=float(i))))

        series_dict = collect_files([str(f) for f in files])
        series = load_series(series_dict)

        assert [p.values["freshness"] for p in series.points] == [0.0, 1.0, 2.0]


# --- extraction rule: meaning subdimensions as flat values ---


def test_collect_extracts_meaning_subdimensions_as_flat_fields() -> None:
    """Meaning subdimensions dict is flattened to top-level value names."""
    subdimensions = {
        "consequence": 0.5,
        "agency": 0.6,
        "causality": 0.7,
    }
    measurement = _meaning_measurement(meaning_score=0.8, subdimensions=subdimensions)
    series_dict = collect([measurement])
    series = load_series(series_dict)

    # All subdimensions + meaning_score are extracted as flat fields
    expected_fields = {"meaning_score", "consequence", "agency", "causality"}
    assert set(series.points[0].values.keys()) == expected_fields
    assert series.points[0].values["consequence"] == 0.5


def test_collect_ignores_non_numeric_values() -> None:
    """Non-numeric values (booleans, strings, etc) are skipped."""
    subdimensions = {
        "valid": 0.5,
        "invalid_bool": True,
        "invalid_string": "text",
        "invalid_null": None,
    }
    measurement = _meaning_measurement(subdimensions=subdimensions)
    series_dict = collect([measurement])
    series = load_series(series_dict)

    # Only the numeric value is extracted
    assert "valid" in series.points[0].values
    assert "invalid_bool" not in series.points[0].values
    assert "invalid_string" not in series.points[0].values
    assert "invalid_null" not in series.points[0].values


def test_collect_handles_empty_subdimensions() -> None:
    """Meaning measurement with empty subdimensions still extracts meaning_score."""
    measurement = _meaning_measurement(meaning_score=0.9, subdimensions={})
    series_dict = collect([measurement])
    series = load_series(series_dict)

    assert "meaning_score" in series.points[0].values
    assert series.points[0].values["meaning_score"] == 0.9


# --- extraction rule: full envelope scores dict ---


def test_collect_extracts_full_envelope_scores() -> None:
    """Envelope scores dict is extracted as values."""
    measurement = build_envelope(
        domain="test_domain",
        score_type="test_type",
        scores={
            "metric_a": 0.1,
            "metric_b": 0.2,
            "metric_c": 0.3,
        },
        frame=None,
        diagnostics=[],
    )
    series_dict = collect([measurement])
    series = load_series(series_dict)

    expected_fields = {"metric_a", "metric_b", "metric_c"}
    assert set(series.points[0].values.keys()) == expected_fields


def test_collect_skips_non_numeric_in_scores_dict() -> None:
    """Non-numeric entries in scores dict are skipped (never added to values).

    Note: build_envelope validates that scores must be numeric, so a properly
    constructed envelope won't have non-numeric values. This test verifies that
    if someone manually creates a malformed measurement, collect skips the
    non-numeric entries without crashing.
    """
    # Manually build a measurement (bypassing build_envelope validation)
    measurement = {
        "domain": "test",
        "score_type": "test",
        "scores": {
            "valid": 0.5,
            "invalid_bool": True,  # Non-numeric
            "invalid_string": "text",  # Non-numeric
        },
        "frame": None,
        "diagnostics": [],
    }
    series_dict = collect([measurement])
    series = load_series(series_dict)

    # Only the numeric value is extracted
    assert series.points[0].values == {"valid": 0.5}


# --- round-trip through load_series ---


def test_collect_output_round_trips_through_load_series() -> None:
    """Collect output is a valid series that loads cleanly."""
    measurements = [
        _meaning_measurement(),
        _quality_measurement(),
    ]
    series_dict = collect([measurements[0]], ids=["m1"])

    # Should load without errors
    series = load_series(series_dict)
    assert series is not None
    assert len(series.diagnostics) == 0  # No diagnostics from loading


def test_collect_multiple_domain_types() -> None:
    """Collect can handle a mix of meaning and full-envelope formats."""
    measurements = [
        _meaning_measurement(meaning_score=0.5),
        _quality_measurement(freshness=0.6),
    ]
    series_dict = collect(measurements)
    series = load_series(series_dict)

    assert len(series.points) == 2
    # First point has meaning-based values
    assert "meaning_score" in series.points[0].values
    # Second point has quality values
    assert "freshness" in series.points[1].values
