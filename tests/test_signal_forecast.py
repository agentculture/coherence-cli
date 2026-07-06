"""Tests for coherence.signal.forecast — the naive next-point extrapolation
engine (the "predict" surface of the signal layer).

Every test is fully OFFLINE (no network, no embeddings -- the signal layer
never touches either). Acceptance criteria (plan task t8):

1. Below the minimum-points threshold (no forecastable field at all) the
   engine raises the user-error exception (``ForecastError``) with a
   machine-readable ``.code``.
2. A constant series forecasts the constant; a strictly linear series
   extends the line -- both asserted numerically (``pytest.approx``).
3. Output includes the method name, the window actually used, and an
   explicit extrapolation label -- both per-field and top-level.

Plus the schema-driven robustness requirements shared with the sibling
engines (trend/pattern/resonance): sparse fields are forecast over their
present values only, a per-field insufficiency is a diagnostic (not a raise)
as long as some other field qualifies, and the engine is source-agnostic
(accepts a preloaded ``Series``, a raw mapping, or a JSON payload).
"""

from __future__ import annotations

import json

import pytest

from coherence.signal.forecast import (
    CODE_FORECAST_INSUFFICIENT_POINTS,
    CODE_FORECAST_NO_FORECASTABLE_FIELDS,
    LABEL_EXTRAPOLATION,
    LINEAR_WEIGHT,
    METHOD_LINEAR_TREND_RECENT_DELTA_BLEND,
    MIN_POINTS,
    WINDOW,
    ForecastError,
    forecast,
)
from coherence.signal.schema import CODE_MISSING_POINTS, Series, SeriesError, load_series

# --- helpers ------------------------------------------------------------


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


# --- acceptance 1: minimum-points guard --------------------------------------


def test_below_minimum_points_raises_forecast_error_with_code() -> None:
    series = _uniform_series("v", [1.0, 2.0])  # 2 present values < MIN_POINTS (3)
    with pytest.raises(ForecastError) as exc_info:
        forecast(series)
    assert exc_info.value.code == CODE_FORECAST_NO_FORECASTABLE_FIELDS


def test_empty_series_raises_forecast_error() -> None:
    with pytest.raises(ForecastError) as exc_info:
        forecast(_series([]))
    assert exc_info.value.code == CODE_FORECAST_NO_FORECASTABLE_FIELDS


def test_series_with_no_numeric_fields_raises_forecast_error() -> None:
    raw = _series([_point("p0", 0, {}), _point("p1", 1, {})])
    with pytest.raises(ForecastError) as exc_info:
        forecast(raw)
    assert exc_info.value.code == CODE_FORECAST_NO_FORECASTABLE_FIELDS


def test_forecast_error_is_a_value_error_with_a_message() -> None:
    assert issubclass(ForecastError, ValueError)
    with pytest.raises(ForecastError) as exc_info:
        forecast(_uniform_series("v", [1.0]))
    assert str(exc_info.value)  # human-readable message is non-empty


def test_one_field_insufficient_other_sufficient_does_not_raise() -> None:
    raw = _series(
        [
            _point("p0", 0, {"a": 1.0, "b": 1.0}),
            _point("p1", 1, {"a": 2.0, "b": 2.0}),
            _point("p2", 2, {"b": 3.0}),  # 'a' absent here -> only 2 present values
        ]
    )
    result = forecast(raw)
    assert result["fields"]["a"]["forecast"] is None
    assert result["fields"]["a"]["n_present"] == 2
    assert result["fields"]["a"]["reason"]
    assert "a" in " ".join(
        d["message"]
        for d in result["diagnostics"]
        if d["code"] == CODE_FORECAST_INSUFFICIENT_POINTS
    )
    assert CODE_FORECAST_INSUFFICIENT_POINTS in _codes(result["diagnostics"])
    assert result["fields"]["b"]["forecast"] is not None
    assert result["fields"]["b"]["forecast"] == pytest.approx(4.0)


def test_structurally_invalid_input_still_raises_series_error() -> None:
    """A malformed series (missing 'points') fails at the loader, not forecast's own guard."""
    with pytest.raises(SeriesError) as exc_info:
        forecast({"nope": "not a series"})
    assert exc_info.value.code == CODE_MISSING_POINTS


# --- acceptance 2: constant forecasts constant, linear extends the line -----


def test_constant_series_forecasts_the_constant() -> None:
    series = _uniform_series("v", [4.0, 4.0, 4.0, 4.0, 4.0])
    field = forecast(series)["fields"]["v"]
    assert field["forecast"] == pytest.approx(4.0)
    assert field["linear_prediction"] == pytest.approx(4.0)
    assert field["delta_prediction"] == pytest.approx(4.0)


def test_constant_series_forecasts_the_constant_below_full_window() -> None:
    # Only 3 present values (< WINDOW), still forecasts the constant exactly.
    series = _uniform_series("v", [7.0, 7.0, 7.0])
    field = forecast(series)["fields"]["v"]
    assert field["forecast"] == pytest.approx(7.0)
    assert field["window"] == 3


def test_strictly_linear_series_extends_the_line() -> None:
    # v(i) = 1 + 2*i -> next value after index 4 (v=9.0) is 11.0.
    series = _uniform_series("v", [1.0, 3.0, 5.0, 7.0, 9.0])
    field = forecast(series)["fields"]["v"]
    assert field["forecast"] == pytest.approx(11.0)
    assert field["linear_prediction"] == pytest.approx(11.0)
    assert field["delta_prediction"] == pytest.approx(11.0)


def test_strictly_linear_series_extends_a_falling_line() -> None:
    # v(i) = 10 - 2*i -> next value after index 2 (v=6.0) is 4.0.
    series = _uniform_series("v", [10.0, 8.0, 6.0])
    field = forecast(series)["fields"]["v"]
    assert field["forecast"] == pytest.approx(4.0)
    assert field["window"] == 3


def test_forecast_uses_only_the_last_window_points() -> None:
    # First 5 points jump wildly; the last 5 points are a clean line (slope 1).
    # If the whole series were fit, the early jump would skew the result away
    # from 406.0 -- clamping to the last WINDOW (5) points must recover it.
    assert WINDOW == 5  # this test's arithmetic assumes the documented default
    levels = [0.0, 100.0, 200.0, 300.0, 400.0, 401.0, 402.0, 403.0, 404.0, 405.0]
    series = _uniform_series("v", levels)
    field = forecast(series)["fields"]["v"]
    assert field["window"] == 5
    assert field["forecast"] == pytest.approx(406.0)


def test_window_clamps_to_available_points_when_fewer_than_window() -> None:
    series = _uniform_series("v", [2.0, 4.0, 6.0])  # 3 present values < WINDOW (5)
    field = forecast(series)["fields"]["v"]
    assert field["n_present"] == 3
    assert field["window"] == 3


# --- acceptance 3: method name, window, extrapolation label -----------------


def test_output_includes_method_window_and_extrapolation_label() -> None:
    series = _uniform_series("v", [1.0, 2.0, 3.0, 4.0, 5.0])
    result = forecast(series)
    assert result["label"] == LABEL_EXTRAPOLATION
    field = result["fields"]["v"]
    assert field["method"] == METHOD_LINEAR_TREND_RECENT_DELTA_BLEND
    assert field["window"] == WINDOW
    assert field["label"] == LABEL_EXTRAPOLATION


def test_blend_weight_is_fifty_fifty_by_default() -> None:
    assert LINEAR_WEIGHT == pytest.approx(0.5)


def test_min_points_constant_is_three() -> None:
    assert MIN_POINTS == 3


# --- sparse fields: gaps handled, not crashed --------------------------------


def test_sparse_field_forecasts_over_present_values_only() -> None:
    raw = _series(
        [
            _point("p0", 0, {"v": 1.0}),
            _point("p1", 1, {"other": 99.0}),  # 'v' absent
            _point("p2", 2, {"v": 3.0}),
            _point("p3", 3, {"other": 99.0}),  # 'v' absent
            _point("p4", 4, {"v": 5.0}),
        ]
    )
    result = forecast(raw)
    field = result["fields"]["v"]
    # Present values in order: [1.0, 3.0, 5.0] -> a clean line, next is 7.0.
    assert field["n_present"] == 3
    assert field["forecast"] == pytest.approx(7.0)


# --- multiple fields analyzed independently ----------------------------------


def test_multiple_fields_forecast_independently() -> None:
    raw = _series(
        [
            _point("p0", 0, {"a": 1.0, "b": 10.0}),
            _point("p1", 1, {"a": 2.0, "b": 8.0}),
            _point("p2", 2, {"a": 3.0, "b": 6.0}),
        ]
    )
    result = forecast(raw)
    assert result["fields"]["a"]["forecast"] == pytest.approx(4.0)
    assert result["fields"]["b"]["forecast"] == pytest.approx(4.0)


# --- source-agnostic input handling -------------------------------------------


def test_forecast_accepts_a_preloaded_series_object() -> None:
    series = _uniform_series("v", [1.0, 2.0, 3.0])
    assert isinstance(series, Series)
    result = forecast(series)
    assert result["fields"]["v"]["forecast"] is not None


def test_forecast_accepts_a_raw_mapping_and_loads_it() -> None:
    raw = _series([_point(f"p{i}", i, {"v": float(i)}) for i in range(3)])
    result = forecast(raw)
    assert result["fields"]["v"]["forecast"] == pytest.approx(3.0)


def test_forecast_accepts_a_json_string() -> None:
    raw = _series([_point(f"p{i}", i, {"v": float(i)}) for i in range(3)])
    result = forecast(json.dumps(raw))
    assert result["fields"]["v"]["forecast"] == pytest.approx(3.0)


def test_loader_diagnostics_are_carried_through_when_given_raw_data() -> None:
    raw = {
        "points": [
            {"id": "p0", "index": 0, "values": {"v": 1.0, "bad": None}},
            {"id": "p1", "index": 1, "values": {"v": 2.0}},
            {"id": "p2", "index": 2, "values": {"v": 3.0}},
        ]
    }
    result = forecast(raw)
    assert any("bad" in d["message"] for d in result["diagnostics"])


def test_domain_is_passed_through_from_the_series() -> None:
    series = _uniform_series("v", [1.0, 2.0, 3.0], domain="warehouse")
    assert forecast(series)["domain"] == "warehouse"


def test_domain_is_none_when_series_has_no_domain() -> None:
    series = _uniform_series("v", [1.0, 2.0, 3.0])
    assert forecast(series)["domain"] is None


# --- top-level shape ----------------------------------------------------------


def test_n_is_total_series_points_not_per_field_count() -> None:
    raw = _series(
        [
            _point("p0", 0, {"v": 1.0}),
            _point("p1", 1, {}),  # no fields at all on this point
            _point("p2", 2, {"v": 3.0}),
            _point("p3", 3, {"v": 5.0}),
        ]
    )
    result = forecast(raw)
    assert result["n"] == 4


def test_fields_are_reported_in_sorted_order_for_deterministic_output() -> None:
    raw = _series(
        [
            _point("p0", 0, {"zeta": 1.0, "alpha": 1.0}),
            _point("p1", 1, {"zeta": 2.0, "alpha": 2.0}),
            _point("p2", 2, {"zeta": 3.0, "alpha": 3.0}),
        ]
    )
    result = forecast(raw)
    assert list(result["fields"]) == ["alpha", "zeta"]


def test_result_is_json_serializable() -> None:
    raw = _series(
        [
            _point("p0", 0, {"v": 1.0}),
            _point("p1", 1, {"v": 2.0}),
            _point("p2", 2, {"v": 3.0}),
        ]
    )
    result = forecast(raw)
    reloaded = json.loads(json.dumps(result))
    assert reloaded["fields"]["v"]["forecast"] == pytest.approx(4.0)
