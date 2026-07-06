"""Offline contract tests for ``coherence.signal.schema`` — the source-agnostic
series input schema and its robust loader.

The signal layer is deliberately blind to *what* produced a series: it consumes
an ordered list of points, each carrying a bag of arbitrarily named numeric
values. These tests prove that source-agnosticism two ways — a hand-written
series with invented value names, and a series mechanically converted from a
REAL ``coherence meaning trend`` result — load through the *same* loader.

They also pin the robustness contract: n=1/2/3+ all load, and malformed values
(missing, null, non-numeric, boolean) are skipped with a diagnostic rather than
crashing. The trend JSON used here is built fully OFFLINE by driving the real
``coherence.meaning.trend`` engine with a synthetic, deterministic ``embed_fn``
(``tests/_meaning_synthetic.py``) over the recorded series fixtures — no network
and no reliance on a live embedding endpoint.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.meaning.trend import trend
from coherence.signal.schema import (
    Series,
    SeriesError,
    SeriesPoint,
    load_series,
    series_from_meaning_trend,
)

from ._meaning_synthetic import synthetic_embed_fn

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "meaning"
_SERIES = _FIXTURES / "series"
_V1, _V2, _V3 = _SERIES / "v1.txt", _SERIES / "v2.txt", _SERIES / "v3.txt"

_MEANING_SUBDIMENSIONS = (
    "consequence",
    "agency",
    "causality",
    "affordance",
    "future_constraint",
)


# --- helpers --------------------------------------------------------------


def _point(pid: str, index: int, values: dict, *, frame=..., timestamp=...) -> dict:
    """Build a raw series-point dict; ``frame``/``timestamp`` omitted unless given."""
    raw: dict = {"id": pid, "index": index, "values": values}
    if frame is not ...:
        raw["frame"] = frame
    if timestamp is not ...:
        raw["timestamp"] = timestamp
    return raw


def _series(points: list[dict], *, domain=...) -> dict:
    raw: dict = {"points": points}
    if domain is not ...:
        raw["domain"] = domain
    return raw


# --- acceptance 1: source-agnostic — hand-written + trend-derived ---------


def test_hand_written_series_with_arbitrary_value_names_loads() -> None:
    """The signal layer never enumerates value names: invented names load intact."""
    raw = _series(
        [
            _point("row-0", 0, {"throughput": 12.5, "widget_gain": -3.0, "q": 0.1}),
            _point("row-1", 1, {"throughput": 13.0, "widget_gain": -2.5, "q": 0.2}),
        ],
        domain="warehouse",
    )
    series = load_series(raw)
    assert isinstance(series, Series)
    assert series.domain == "warehouse"
    assert series.diagnostics == []
    assert [p.id for p in series.points] == ["row-0", "row-1"]
    assert series.points[0].values == {"throughput": 12.5, "widget_gain": -3.0, "q": 0.1}
    # The value names are caller-defined; the loader surfaces them verbatim.
    assert series.field_names() == {"throughput", "widget_gain", "q"}


def test_series_converted_from_real_meaning_trend_loads() -> None:
    """A REAL meaning-trend result (built offline) converts to a valid series."""
    trend_json = trend([_V1, _V2, _V3], embed_fn=synthetic_embed_fn)
    assert trend_json["n"] == 3  # sanity: three points came back

    raw = series_from_meaning_trend(trend_json)
    series = load_series(raw)

    assert series.domain == "meaning"
    assert series.diagnostics == []
    assert len(series.points) == 3
    # Each point's id is the source path, in order.
    assert [p.id for p in series.points] == [str(_V1), str(_V2), str(_V3)]
    assert [p.index for p in series.points] == [0, 1, 2]
    # meaning_score + the five subdimensions are surfaced as flat numeric fields.
    expected_fields = {"meaning_score", *_MEANING_SUBDIMENSIONS}
    for point in series.points:
        assert set(point.values) == expected_fields
        for value in point.values.values():
            assert isinstance(value, float)
    # The per-point meaning_score matches the trend engine's raw levels.
    trend_scores = [pt["meaning_score"] for pt in trend_json["points"]]
    assert [p.values["meaning_score"] for p in series.points] == pytest.approx(trend_scores)


def test_converter_returns_schema_valid_dict_not_normalized_object() -> None:
    """``series_from_meaning_trend`` produces the *input* dict shape, not a Series."""
    trend_json = trend([_V1, _V2], embed_fn=synthetic_embed_fn)
    raw = series_from_meaning_trend(trend_json)
    assert isinstance(raw, dict)
    assert set(raw) >= {"domain", "points"}
    assert isinstance(raw["points"], list) and len(raw["points"]) == 2
    for i, point in enumerate(raw["points"]):
        assert set(point) >= {"id", "index", "timestamp", "values", "frame"}
        assert point["index"] == i


def test_converter_carries_trend_frame_onto_every_point() -> None:
    """A frame on the trend result (frames task, later) is carried to each point."""
    frame = {"embedding_model": "m", "embedding_endpoint": "e"}
    trend_json = trend([_V1, _V2], embed_fn=synthetic_embed_fn)
    trend_json["frame"] = frame  # simulate the additive frame block a later task adds

    raw = series_from_meaning_trend(trend_json)
    series = load_series(raw)
    assert all(p.frame == frame for p in series.points)


# --- acceptance 2: n=1 / n=2 / n=3+, malformed values skipped-with-diag ----


@pytest.mark.parametrize("n", [1, 2, 3, 5])
def test_series_of_length_n_loads(n: int) -> None:
    raw = _series([_point(f"p{i}", i, {"v": float(i)}) for i in range(n)])
    series = load_series(raw)
    assert len(series.points) == n
    assert [p.index for p in series.points] == list(range(n))
    assert series.diagnostics == []


def test_missing_values_key_yields_empty_values_with_diagnostic() -> None:
    raw = {"points": [{"id": "p0", "index": 0}]}  # no 'values' at all
    series = load_series(raw)
    assert len(series.points) == 1
    assert series.points[0].values == {}
    assert any(d["code"] for d in series.diagnostics)
    assert "p0" in " ".join(d["message"] for d in series.diagnostics)


def test_null_value_is_skipped_with_diagnostic_point_survives() -> None:
    raw = _series([_point("p0", 0, {"good": 1.0, "bad": None})])
    series = load_series(raw)
    assert series.points[0].values == {"good": 1.0}  # bad dropped
    assert len(series.points) == 1
    assert any("bad" in d["message"] for d in series.diagnostics)


def test_non_numeric_string_value_is_skipped_with_diagnostic() -> None:
    raw = _series([_point("p0", 0, {"good": 2.0, "label": "high"})])
    series = load_series(raw)
    assert series.points[0].values == {"good": 2.0}
    assert any("label" in d["message"] for d in series.diagnostics)


def test_booleans_are_not_numeric_values() -> None:
    """``True``/``False`` must NOT be coerced to 1.0/0.0 — they are skipped."""
    raw = _series([_point("p0", 0, {"real": 0.5, "flag_t": True, "flag_f": False})])
    series = load_series(raw)
    assert series.points[0].values == {"real": 0.5}
    dropped = " ".join(d["message"] for d in series.diagnostics)
    assert "flag_t" in dropped and "flag_f" in dropped


def test_non_string_value_name_is_skipped_with_diagnostic() -> None:
    raw = _series([{"id": "p0", "index": 0, "values": {"ok": 1.0, 7: 2.0}}])
    series = load_series(raw)
    assert series.points[0].values == {"ok": 1.0}
    assert len(series.diagnostics) >= 1


def test_point_that_is_not_a_dict_is_skipped_with_diagnostic() -> None:
    raw = {"points": [{"id": "p0", "index": 0, "values": {"v": 1.0}}, "not-a-point", 42]}
    series = load_series(raw)
    assert [p.id for p in series.points] == ["p0"]
    assert len(series.diagnostics) >= 2  # both bad entries flagged


def test_numeric_values_are_normalized_to_float() -> None:
    raw = _series([_point("p0", 0, {"count": 3, "ratio": 0.5})])
    series = load_series(raw)
    assert series.points[0].values == {"count": 3.0, "ratio": 0.5}
    assert all(isinstance(v, float) for v in series.points[0].values.values())


# --- per-point frame: optional, normalized to explicit null ---------------


def test_point_without_frame_normalizes_to_explicit_null() -> None:
    raw = _series([_point("p0", 0, {"v": 1.0})])  # frame omitted
    series = load_series(raw)
    assert series.points[0].frame is None


def test_point_with_explicit_null_frame_stays_null() -> None:
    raw = _series([_point("p0", 0, {"v": 1.0}, frame=None)])
    series = load_series(raw)
    assert series.points[0].frame is None


def test_per_point_frames_are_surfaced_for_a_later_mixed_frame_guard() -> None:
    """Distinct per-point frames survive normalization (enables a mixed-frame guard)."""
    frame_a = {"embedding_model": "model-a"}
    frame_b = {"embedding_model": "model-b"}
    raw = _series(
        [
            _point("p0", 0, {"v": 1.0}, frame=frame_a),
            _point("p1", 1, {"v": 2.0}, frame=frame_b),
        ]
    )
    series = load_series(raw)
    assert series.points[0].frame == frame_a
    assert series.points[1].frame == frame_b


def test_frame_of_wrong_type_normalized_to_null_with_diagnostic() -> None:
    raw = _series([_point("p0", 0, {"v": 1.0}, frame="not-a-frame")])
    series = load_series(raw)
    assert series.points[0].frame is None
    assert any("frame" in d["message"] for d in series.diagnostics)


def test_diagnostics_list_is_appendable() -> None:
    """A later task (mixed-frame guard) must be able to append its own diagnostics."""
    raw = _series([_point("p0", 0, {"v": 1.0})])
    series = load_series(raw)
    assert isinstance(series.diagnostics, list)
    series.diagnostics.append({"code": "mixed_frame", "message": "example guard"})
    assert series.diagnostics[-1]["code"] == "mixed_frame"


# --- timestamp / index / domain normalization -----------------------------


def test_timestamp_absent_normalizes_to_null() -> None:
    raw = _series([_point("p0", 0, {"v": 1.0})])
    series = load_series(raw)
    assert series.points[0].timestamp is None


def test_timestamp_string_is_preserved() -> None:
    raw = _series([_point("p0", 0, {"v": 1.0}, timestamp="2026-07-06T00:00:00Z")])
    series = load_series(raw)
    assert series.points[0].timestamp == "2026-07-06T00:00:00Z"


def test_absent_domain_normalizes_to_none() -> None:
    raw = _series([_point("p0", 0, {"v": 1.0})])  # no domain
    series = load_series(raw)
    assert series.domain is None


def test_non_string_domain_dropped_with_diagnostic() -> None:
    raw = _series([_point("p0", 0, {"v": 1.0})], domain=123)
    series = load_series(raw)
    assert series.domain is None
    assert any("domain" in d["message"] for d in series.diagnostics)


def test_missing_id_is_synthesized_with_diagnostic() -> None:
    raw = {"points": [{"index": 0, "values": {"v": 1.0}}]}
    series = load_series(raw)
    assert isinstance(series.points[0].id, str) and series.points[0].id
    assert any("id" in d["message"] for d in series.diagnostics)


def test_provided_index_mismatch_uses_position_with_diagnostic() -> None:
    raw = {"points": [{"id": "p0", "index": 9, "values": {"v": 1.0}}]}
    series = load_series(raw)
    assert series.points[0].index == 0  # canonicalized to list position
    assert any("index" in d["message"] for d in series.diagnostics)


# --- top-level structural failures raise (never a silent empty series) ----


@pytest.mark.parametrize("bad", [42, ["a", "b"], None, 3.14])
def test_non_mapping_input_raises_series_error(bad) -> None:
    with pytest.raises(SeriesError) as excinfo:
        load_series(bad)
    assert isinstance(excinfo.value.code, str) and excinfo.value.code


def test_missing_points_key_raises_series_error() -> None:
    with pytest.raises(SeriesError):
        load_series({"domain": "meaning"})


def test_points_not_a_list_raises_series_error() -> None:
    with pytest.raises(SeriesError):
        load_series({"points": {"not": "a list"}})


def test_structural_and_missing_points_have_distinct_codes() -> None:
    with pytest.raises(SeriesError) as e1:
        load_series(42)
    with pytest.raises(SeriesError) as e2:
        load_series({"domain": "x"})
    assert e1.value.code != e2.value.code


# --- JSON string convenience + round-trip ---------------------------------


def test_loader_accepts_a_json_string() -> None:
    raw = _series([_point("p0", 0, {"v": 1.0})], domain="d")
    series = load_series(json.dumps(raw))
    assert series.domain == "d"
    assert series.points[0].values == {"v": 1.0}


def test_invalid_json_string_raises_series_error() -> None:
    with pytest.raises(SeriesError):
        load_series("{not valid json")


def test_to_dict_round_trips_through_loader() -> None:
    raw = _series(
        [
            _point("p0", 0, {"a": 1.0, "b": 2.0}, frame={"m": "x"}),
            _point("p1", 1, {"a": 1.5, "b": 2.5}, frame=None, timestamp="t"),
        ],
        domain="meaning",
    )
    series = load_series(raw)
    reloaded = load_series(series.to_dict())
    assert reloaded.domain == series.domain
    assert [p.to_dict() for p in reloaded.points] == [p.to_dict() for p in series.points]


def test_seriespoint_is_a_dataclass_like_record() -> None:
    raw = _series([_point("p0", 0, {"v": 1.0})])
    point = load_series(raw).points[0]
    assert isinstance(point, SeriesPoint)
    assert point.id == "p0" and point.index == 0 and point.values == {"v": 1.0}
