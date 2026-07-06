"""Tests for coherence.signal.trend — the source-agnostic f'/f'' trend engine.

Every test is fully OFFLINE (no network, no embeddings — the signal layer
never touches either). Acceptance criteria (plan task t4):

1. 2 points yield f' (first difference), 3+ points yield f'' (second
   difference), per field; 1 point yields an explicit too-short diagnostic
   and no differences.
2. Monotonicity (increasing/decreasing/mixed) and a simple volatility measure
   are reported per field.

Plus the schema-driven robustness requirement: fields missing from some
points (sparse values, allowed by the series schema) are computed over the
points where they ARE present, with a diagnostic when gaps exist.
"""

from __future__ import annotations

import json
import statistics

import pytest

from coherence.signal.schema import Series, load_series
from coherence.signal.trend import (
    CODE_TREND_NO_FIELDS,
    CODE_TREND_SECOND_UNAVAILABLE,
    CODE_TREND_SPARSE_FIELD,
    CODE_TREND_TOO_SHORT,
    analyze_field,
    first_difference,
    second_difference,
    trend,
)

# --- helpers ----------------------------------------------------------------


def _point(pid: str, index: int, values: dict) -> dict:
    return {"id": pid, "index": index, "values": values}


def _series(points: list[dict], *, domain: str | None = None) -> dict:
    raw: dict = {"points": points}
    if domain is not None:
        raw["domain"] = domain
    return raw


def _uniform_series(field: str, levels: list[float], *, domain: str | None = None) -> Series:
    """Build a loaded Series where every point carries one field's value."""
    raw = _series([_point(f"p{i}", i, {field: v}) for i, v in enumerate(levels)], domain=domain)
    return load_series(raw)


def _codes(diagnostics: list[dict]) -> set:
    return {d["code"] for d in diagnostics}


# --- pure difference functions (reused semantics from meaning.trend) --------


def test_first_difference_is_per_step_delta() -> None:
    assert first_difference([1.0, 3.0, 6.0, 10.0]) == [2.0, 3.0, 4.0]


def test_first_difference_of_fewer_than_two_is_empty() -> None:
    assert first_difference([5.0]) == []
    assert first_difference([]) == []


def test_second_difference_is_diff_of_first_difference() -> None:
    assert second_difference([1.0, 3.0, 6.0, 10.0]) == [1.0, 1.0]


def test_second_difference_equals_first_difference_applied_twice() -> None:
    levels = [2.0, 5.0, 9.0, 20.0, 22.0]
    assert second_difference(levels) == first_difference(first_difference(levels))


def test_second_difference_of_fewer_than_three_is_empty() -> None:
    assert second_difference([1.0, 2.0]) == []


# --- acceptance 1: point-count gates (1 / 2 / 3+) ---------------------------


def test_one_point_yields_too_short_diagnostic_and_no_differences() -> None:
    series = _uniform_series("v", [1.0])
    result = trend(series)
    field = result["fields"]["v"]
    assert field["n_present"] == 1
    assert field["first"]["values"] is None
    assert field["first"]["reason"]
    assert field["second"]["values"] is None
    assert field["second"]["reason"]
    assert field["monotonicity"] is None
    assert field["volatility"] is None
    assert CODE_TREND_TOO_SHORT in _codes(field["diagnostics"])
    assert "v" in " ".join(d["message"] for d in field["diagnostics"])
    # And the top-level diagnostics roll the field-level ones up.
    assert CODE_TREND_TOO_SHORT in _codes(result["diagnostics"])


def test_two_points_yield_first_difference_only() -> None:
    series = _uniform_series("v", [1.0, 3.0])
    result = trend(series)
    field = result["fields"]["v"]
    assert field["n_present"] == 2
    assert field["first"]["values"] == [2.0]
    assert field["first"]["reason"] is None
    assert field["second"]["values"] is None
    assert field["second"]["reason"]
    assert CODE_TREND_SECOND_UNAVAILABLE in _codes(field["diagnostics"])
    assert CODE_TREND_TOO_SHORT not in _codes(field["diagnostics"])


def test_three_points_yield_first_and_second_difference() -> None:
    series = _uniform_series("v", [1.0, 3.0, 6.0])
    result = trend(series)
    field = result["fields"]["v"]
    assert field["n_present"] == 3
    assert field["first"]["values"] == [2.0, 3.0]
    assert field["first"]["reason"] is None
    assert field["second"]["values"] == [1.0]
    assert field["second"]["reason"] is None
    assert CODE_TREND_SECOND_UNAVAILABLE not in _codes(field["diagnostics"])
    assert CODE_TREND_TOO_SHORT not in _codes(field["diagnostics"])


def test_five_points_yield_full_length_differences() -> None:
    series = _uniform_series("v", [1.0, 2.0, 4.0, 7.0, 11.0])
    result = trend(series)
    field = result["fields"]["v"]
    assert field["n_present"] == 5
    assert field["first"]["values"] == [1.0, 2.0, 3.0, 4.0]
    assert field["second"]["values"] == [1.0, 1.0, 1.0]


# --- acceptance 2: monotonicity + volatility --------------------------------


def test_monotonicity_increasing() -> None:
    series = _uniform_series("v", [1.0, 2.0, 4.0])
    assert trend(series)["fields"]["v"]["monotonicity"] == "increasing"


def test_monotonicity_decreasing() -> None:
    series = _uniform_series("v", [10.0, 7.0, 3.0])
    assert trend(series)["fields"]["v"]["monotonicity"] == "decreasing"


def test_monotonicity_mixed() -> None:
    series = _uniform_series("v", [1.0, 3.0, 2.0, 5.0])
    assert trend(series)["fields"]["v"]["monotonicity"] == "mixed"


def test_monotonicity_constant() -> None:
    series = _uniform_series("v", [5.0, 5.0, 5.0, 5.0])
    result = trend(series)["fields"]["v"]
    assert result["monotonicity"] == "constant"
    assert result["volatility"] == pytest.approx(0.0)


def test_monotonicity_none_when_too_short() -> None:
    series = _uniform_series("v", [1.0])
    assert trend(series)["fields"]["v"]["monotonicity"] is None


def test_volatility_is_population_stdev_of_first_differences() -> None:
    levels = [1.0, 3.0, 2.0, 5.0]
    diffs = first_difference(levels)
    expected = statistics.pstdev(diffs)
    series = _uniform_series("v", levels)
    assert trend(series)["fields"]["v"]["volatility"] == pytest.approx(expected)


def test_oscillating_series_is_more_volatile_than_steady_trend() -> None:
    steady = _uniform_series("v", [1.0, 2.0, 3.0, 4.0, 5.0])
    jagged = _uniform_series("v", [1.0, 5.0, 1.0, 5.0, 1.0])
    steady_vol = trend(steady)["fields"]["v"]["volatility"]
    jagged_vol = trend(jagged)["fields"]["v"]["volatility"]
    assert steady_vol == pytest.approx(0.0)
    assert jagged_vol > steady_vol


def test_volatility_none_when_too_short() -> None:
    series = _uniform_series("v", [1.0])
    assert trend(series)["fields"]["v"]["volatility"] is None


# --- sparse fields: gaps handled, diagnosed, not crashed --------------------


def test_field_missing_from_some_points_computes_over_present_values() -> None:
    raw = _series(
        [
            _point("p0", 0, {"v": 1.0}),
            _point("p1", 1, {"v": 2.0}),
            _point("p2", 2, {"other": 99.0}),  # 'v' absent here
            _point("p3", 3, {"v": 5.0}),
        ]
    )
    result = trend(raw)
    field = result["fields"]["v"]
    assert field["n_present"] == 3
    # Differenced over the present subsequence [1.0, 2.0, 5.0], gap ignored positionally.
    assert field["first"]["values"] == [1.0, 3.0]
    assert field["second"]["values"] == [2.0]
    assert CODE_TREND_SPARSE_FIELD in _codes(field["diagnostics"])
    message = " ".join(d["message"] for d in field["diagnostics"])
    assert "v" in message and "2" in message  # names the missing point's index


def test_sparse_field_diagnostic_absent_when_field_present_everywhere() -> None:
    series = _uniform_series("v", [1.0, 2.0, 3.0])
    field = trend(series)["fields"]["v"]
    assert CODE_TREND_SPARSE_FIELD not in _codes(field["diagnostics"])


# --- multiple fields analyzed independently ---------------------------------


def test_multiple_fields_analyzed_independently() -> None:
    raw = _series(
        [
            _point("p0", 0, {"a": 1.0, "b": 10.0}),
            _point("p1", 1, {"a": 2.0, "b": 8.0}),
            _point("p2", 2, {"a": 4.0, "b": 6.0}),
        ]
    )
    result = trend(raw)
    assert set(result["fields"]) == {"a", "b"}
    assert result["fields"]["a"]["monotonicity"] == "increasing"
    assert result["fields"]["b"]["monotonicity"] == "decreasing"


def test_analyze_field_directly_matches_trend_output() -> None:
    series = _uniform_series("v", [1.0, 2.0, 4.0])
    direct = analyze_field(series, "v")
    via_trend = trend(series)["fields"]["v"]
    assert direct == via_trend


# --- no analyzable fields ----------------------------------------------------


def test_series_with_no_numeric_fields_yields_no_fields_diagnostic() -> None:
    raw = _series([_point("p0", 0, {})])
    result = trend(raw)
    assert result["fields"] == {}
    assert CODE_TREND_NO_FIELDS in _codes(result["diagnostics"])


def test_empty_series_yields_no_fields_diagnostic() -> None:
    result = trend(_series([]))
    assert result["n"] == 0
    assert result["fields"] == {}
    assert CODE_TREND_NO_FIELDS in _codes(result["diagnostics"])


# --- source-agnostic input handling ------------------------------------------


def test_trend_accepts_a_preloaded_series_object() -> None:
    series = _uniform_series("v", [1.0, 2.0])
    assert isinstance(series, Series)
    result = trend(series)
    assert result["fields"]["v"]["first"]["values"] == [1.0]


def test_trend_accepts_a_raw_mapping_and_loads_it() -> None:
    raw = _series([_point("p0", 0, {"v": 1.0}), _point("p1", 1, {"v": 4.0})])
    result = trend(raw)
    assert result["fields"]["v"]["first"]["values"] == [3.0]


def test_trend_accepts_a_json_string() -> None:
    raw = _series([_point("p0", 0, {"v": 1.0}), _point("p1", 1, {"v": 4.0})])
    result = trend(json.dumps(raw))
    assert result["fields"]["v"]["first"]["values"] == [3.0]


def test_loader_diagnostics_are_carried_through_when_given_raw_data() -> None:
    raw = {"points": [{"id": "p0", "index": 0, "values": {"v": 1.0, "bad": None}}]}
    result = trend(raw)
    assert any("bad" in d["message"] for d in result["diagnostics"])


def test_domain_is_passed_through_from_the_series() -> None:
    series = _uniform_series("v", [1.0, 2.0], domain="warehouse")
    assert trend(series)["domain"] == "warehouse"


def test_domain_is_none_when_series_has_no_domain() -> None:
    series = _uniform_series("v", [1.0, 2.0])
    assert trend(series)["domain"] is None


# --- top-level shape ----------------------------------------------------------


def test_n_is_total_series_points_not_per_field_count() -> None:
    raw = _series(
        [
            _point("p0", 0, {"v": 1.0}),
            _point("p1", 1, {}),  # no fields at all on this point
            _point("p2", 2, {"v": 3.0}),
        ]
    )
    result = trend(raw)
    assert result["n"] == 3


def test_fields_are_reported_in_sorted_order_for_deterministic_output() -> None:
    raw = _series(
        [
            _point("p0", 0, {"zeta": 1.0, "alpha": 1.0}),
            _point("p1", 1, {"zeta": 2.0, "alpha": 2.0}),
        ]
    )
    result = trend(raw)
    assert list(result["fields"]) == ["alpha", "zeta"]


def test_result_is_json_serializable() -> None:
    raw = _series(
        [
            _point("p0", 0, {"v": 1.0}),
            _point("p1", 1, {"v": 2.0}),
            _point("p2", 2, {"v": 4.0}),
        ]
    )
    result = trend(raw)
    reloaded = json.loads(json.dumps(result))
    assert reloaded["fields"]["v"]["first"]["values"] == [1.0, 2.0]
