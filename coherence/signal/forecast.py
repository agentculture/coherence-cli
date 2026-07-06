"""coherence.signal.forecast — naive next-point extrapolation over a loaded
series, per numeric field.

This is the "predict" surface of the :mod:`coherence.signal` layer: it
projects each field's *next* value from its recent history. It is
deliberately, unmissably labeled **extrapolation**, never prophecy — a
mechanical continuation of a declared frame's recent trajectory, nothing
more. A caller who mistakes this for a promise about the future has
misread the label, not the math.

Method — "linear trend + recent-delta blend"
----------------------------------------------
For each numeric field, over the last :data:`WINDOW` *present* values
(clamped to however many are actually available)::

    linear_prediction = least-squares line fit over the window,
                         extrapolated one step past its last point
    delta_prediction   = last value + mean(first differences of the window)
    forecast           = LINEAR_WEIGHT * linear_prediction
                          + (1 - LINEAR_WEIGHT) * delta_prediction

``first_difference`` is reused directly from :mod:`coherence.signal.trend`
so the "recent delta" is computed with the exact same per-step semantics
the trend engine reports as f' — no reimplementation, no drift between the
two engines' idea of "a step".

Every constant above (:data:`WINDOW`, :data:`MIN_POINTS`,
:data:`LINEAR_WEIGHT`) is a module constant so the method is fully
documented and reproducible: nothing here is fit or tuned against data.

Minimum-points guard
---------------------
A least-squares line and a meaningful "recent delta" both need more than a
couple of points to mean anything. A field with fewer than
:data:`MIN_POINTS` present values is simply **not forecast**:

* If *some* fields qualify and others don't, the short fields get a
  ``null`` forecast plus a :data:`CODE_FORECAST_INSUFFICIENT_POINTS`
  diagnostic (per-field, not fatal) — the qualifying fields are still
  forecast normally.
* If **no** field in the whole series qualifies (including a series with no
  numeric fields at all), there is nothing useful to return, so
  :func:`forecast` raises :class:`ForecastError` — a
  :class:`~coherence.signal.schema.SeriesError`-style exception carrying a
  machine-readable :attr:`~ForecastError.code`
  (:data:`CODE_FORECAST_NO_FORECASTABLE_FIELDS`) so a CLI layer can map it
  to exit 1 with a hint, the same convention the schema loader uses for its
  own structural failures.

Output shape
------------
:func:`forecast` returns a plain, JSON-serializable ``dict``::

    {
      "n": <int>,                  # total points in the series
      "domain": <str|None>,        # passthrough of Series.domain
      "label": "extrapolation",    # top-level, unmissable extrapolation label
      "fields": {
        "<field name>": {
          "forecast": <float|None>,
          "method": "linear_trend_recent_delta_blend"|None,
          "window": <int|None>,     # points actually used (<= WINDOW)
          "label": "extrapolation"|None,
          "n_present": <int>,
          "linear_prediction": <float>,   # present only when forecast
          "delta_prediction": <float>,    # present only when forecast
          "reason": <str>,                # present only when NOT forecast
        },
        ...                         # one entry per name in series.field_names(),
                                     # in sorted order for deterministic output
      },
      "diagnostics": [{"code": str, "message": str}, ...]
    }

Accepted input
--------------
:func:`forecast` accepts an already-loaded
:class:`~coherence.signal.schema.Series`, OR anything
:func:`~coherence.signal.schema.load_series` accepts (a raw mapping, or a
JSON ``str``/``bytes`` payload) — mirroring :func:`coherence.signal.trend.trend`,
it loads the input first when it isn't already a ``Series``, and the
loader's own diagnostics are carried into the returned ``diagnostics`` list.

Sparse fields
-------------
As with :mod:`coherence.signal.trend` and :mod:`coherence.signal.pattern`,
a field need not appear on every point. The window is drawn from the
field's *present* values only, in series order, treating a gap as simply
absent (never interpolated).
"""

from __future__ import annotations

import statistics
from typing import Any, Mapping

import numpy as np

from coherence.signal.schema import Series, load_series
from coherence.signal.trend import first_difference

# --- machine-readable codes --------------------------------------------------
#
# Per-field diagnostic (never raised -- other fields may still be forecast):
CODE_FORECAST_INSUFFICIENT_POINTS = "forecast_insufficient_points"
# Raised (as ForecastError) only when NOT A SINGLE field is forecastable:
CODE_FORECAST_NO_FORECASTABLE_FIELDS = "forecast_no_forecastable_fields"

# --- method / label constants -------------------------------------------------
METHOD_LINEAR_TREND_RECENT_DELTA_BLEND = "linear_trend_recent_delta_blend"
LABEL_EXTRAPOLATION = "extrapolation"

# --- thresholds ----------------------------------------------------------------
#
# Every threshold below is a module constant precisely so the method is fully
# documented, reproducible, and (if ever needed) tunable in one place.

# The number of most-recent PRESENT values used for the linear fit and the
# recent-delta mean, clamped to however many are actually available. Five is
# enough to smooth a single noisy step without dragging in ancient history
# that a "next point" forecast has no business considering.
WINDOW = 5

# Fewer than this many present values and neither a least-squares line nor a
# "recent delta" mean anything more than an artifact of a couple of points:
# 2 points always lie exactly on *some* line (never a meaningful fit) and give
# only one first difference (not a "mean" of anything). 3 is the first point
# count where the fit and the delta mean both carry real information.
MIN_POINTS = 3

# Weight given to the linear-fit prediction in the final blend; the remainder
# (1 - this) goes to the recent-delta prediction. 0.5 is a deliberate, neutral
# 50/50 split -- neither component is assumed more reliable than the other.
LINEAR_WEIGHT = 0.5


class ForecastError(ValueError):
    """Raised when NOT A SINGLE series field has enough points to forecast.

    Mirrors :class:`coherence.signal.schema.SeriesError`: a ``ValueError``
    carrying a machine-readable :attr:`code` alongside the human-readable
    message, so a CLI layer can branch on the failure kind (map it to exit 1
    with a hint) rather than parsing strings. Reserved for the "nothing at
    all to forecast" case -- a single under-populated field among otherwise
    forecastable ones is a per-field diagnostic, never a raise.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _diag(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _insufficient_reason(field: str, n_present: int) -> str:
    return (
        f"field {field!r}: only {n_present} present value(s); forecasting needs at "
        f"least {MIN_POINTS} to fit a trend and a recent delta, so no forecast was "
        "computed for this field"
    )


def _linear_prediction(windowed: list[float]) -> float:
    """Least-squares line over ``windowed`` (x = 0..len-1), extended one step past it."""
    x = np.arange(len(windowed), dtype=np.float64)
    y = np.asarray(windowed, dtype=np.float64)
    slope, intercept = np.polyfit(x, y, 1)
    return float(slope * len(windowed) + intercept)


def _delta_prediction(windowed: list[float]) -> float:
    """The last windowed value plus the mean of the windowed first differences."""
    diffs = first_difference(windowed)
    mean_delta = statistics.mean(diffs)
    return windowed[-1] + mean_delta


def _forecast_field(
    series: Series, field: str, diagnostics: list[dict[str, str]]
) -> dict[str, Any]:
    """Forecast one named field, or record why it can't be (see module docstring)."""
    values = [point.values[field] for point in series.points if field in point.values]
    n_present = len(values)

    if n_present < MIN_POINTS:
        reason = _insufficient_reason(field, n_present)
        diagnostics.append(_diag(CODE_FORECAST_INSUFFICIENT_POINTS, reason))
        return {
            "forecast": None,
            "method": None,
            "window": None,
            "label": None,
            "n_present": n_present,
            "reason": reason,
        }

    window = min(WINDOW, n_present)
    windowed = values[-window:]
    linear_pred = _linear_prediction(windowed)
    delta_pred = _delta_prediction(windowed)
    value = LINEAR_WEIGHT * linear_pred + (1.0 - LINEAR_WEIGHT) * delta_pred

    return {
        "forecast": value,
        "method": METHOD_LINEAR_TREND_RECENT_DELTA_BLEND,
        "window": window,
        "label": LABEL_EXTRAPOLATION,
        "n_present": n_present,
        "linear_prediction": linear_pred,
        "delta_prediction": delta_pred,
    }


def _no_forecastable_fields_message(field_names: list[str]) -> str:
    if not field_names:
        return "series has no numeric fields to forecast"
    return (
        f"no field has at least {MIN_POINTS} present value(s); forecasting needs a "
        f"minimum of {MIN_POINTS} points per field and none of {field_names} qualify"
    )


def forecast(data: Series | Mapping[str, Any] | str | bytes) -> dict[str, Any]:
    """Extrapolate the next value of every numeric field in a series.

    Accepts an already-loaded :class:`~coherence.signal.schema.Series`, or
    anything :func:`~coherence.signal.schema.load_series` accepts (a raw
    mapping, or JSON ``str``/``bytes``) -- loading it first. See the module
    docstring for the exact JSON output shape and the "linear trend + recent
    delta blend" method.

    Args:
        data: A :class:`Series`, or a raw series mapping / JSON payload.

    Returns:
        A JSON-serializable ``dict`` (see module docstring). Every forecast
        is explicitly labeled ``"extrapolation"`` -- this is a mechanical
        continuation of recent history, not a prediction about the future.

    Raises:
        SeriesError: Propagated from
            :func:`~coherence.signal.schema.load_series` when ``data`` is not
            a ``Series`` and is structurally uninterpretable.
        ForecastError: When NOT A SINGLE field in the series has at least
            :data:`MIN_POINTS` present values -- there is nothing forecastable
            at all. Carries a machine-readable :attr:`ForecastError.code`
            (:data:`CODE_FORECAST_NO_FORECASTABLE_FIELDS`).
    """
    series = data if isinstance(data, Series) else load_series(data)
    diagnostics: list[dict[str, str]] = list(series.diagnostics)

    field_names = sorted(series.field_names())
    fields: dict[str, dict[str, Any]] = {}
    forecastable = 0
    for name in field_names:
        result = _forecast_field(series, name, diagnostics)
        fields[name] = result
        if result["forecast"] is not None:
            forecastable += 1

    if forecastable == 0:
        raise ForecastError(
            CODE_FORECAST_NO_FORECASTABLE_FIELDS,
            _no_forecastable_fields_message(field_names),
        )

    return {
        "n": len(series.points),
        "domain": series.domain,
        "label": LABEL_EXTRAPOLATION,
        "fields": fields,
        "diagnostics": diagnostics,
    }


__all__ = [
    "forecast",
    "ForecastError",
    "CODE_FORECAST_INSUFFICIENT_POINTS",
    "CODE_FORECAST_NO_FORECASTABLE_FIELDS",
    "METHOD_LINEAR_TREND_RECENT_DELTA_BLEND",
    "LABEL_EXTRAPOLATION",
    "WINDOW",
    "MIN_POINTS",
    "LINEAR_WEIGHT",
]
