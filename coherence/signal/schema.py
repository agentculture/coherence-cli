"""coherence.signal.schema — the source-agnostic series input schema + loader.

This module defines the one shape every ``coherence signal`` engine consumes
(trend, pattern, resonance, forecast, collect) and a robust loader that turns a
raw series dict into a normalized, typed in-memory representation. The schema is
the contract for the whole signal layer, so it is documented in full at
``docs/signal-series.md``; this docstring is the code-side summary.

The series shape
----------------
A series is a JSON object with two keys::

    {
      "domain": "meaning",              # OPTIONAL producing-dimension name
      "points": [                       # ordered list of measurement points
        {"id": "v1.md", "index": 0, "timestamp": null,
         "values": {"meaning_score": 0.41, "agency": 0.33},
         "frame": null}
      ]
    }

* ``domain`` — an *optional* string naming the dimension that produced the
  series (``"meaning"``, ``"quality"``, ``"investiture"``, ...). The signal
  layer never branches on it; it exists only as a human-readable label. Absent
  or non-string → normalized to ``None`` (a diagnostic notes a non-string).
* ``points`` — an ordered list. Order is the source of truth for series
  position; the normalized ``index`` is always the list position.
* Per point:
  * ``id`` (str) — a human-readable label for the point (a filename, a version
    tag). Missing/non-string → synthesized as ``"point-<pos>"`` with a
    diagnostic.
  * ``index`` (int) — the point's position. Canonicalized to the list position;
    a provided value that disagrees earns an ``index_mismatch`` diagnostic.
  * ``timestamp`` — nullable; a wall-clock label (ISO string or epoch number)
    or ``null``. The signal layer does no time-axis math (differences are
    per-step), so this is carried through untouched. Absent → ``None``.
  * ``values`` (dict) — an open map of **arbitrarily named numeric** values.
    The names are caller-defined and NEVER enumerated by the signal layer.
    Each value must be a real ``int``/``float`` (``bool`` is NOT numeric) and
    is normalized to ``float``; every missing / null / non-numeric / boolean
    entry, and every non-string name, is *skipped with a diagnostic* — never a
    crash. A point with no salvageable values survives with ``values == {}``.
  * ``frame`` — an OPTIONAL per-point provenance block: the measurement frame
    (embedding model, endpoint, anchor set, ...) that produced this point,
    mirroring the ``frame`` key of the shared measurement envelope in
    :mod:`coherence.schema`. May be a dict, ``null``, or absent; absent/null →
    normalized to explicit ``None``. Per-point frames are surfaced on the
    normalized point so a later mixed-frame guard can compare them.

The loader contract
-------------------
:func:`load_series` returns a :class:`Series` — ``domain``, a list of
:class:`SeriesPoint`, and a **mutable** ``diagnostics`` list of
``{"code", "message"}`` dicts (the same shape as
:mod:`coherence.meaning.diagnostics` and the envelope's diagnostics). The list
is deliberately appendable so a later task (the mixed-frame guard) can plug in
by walking ``series.points`` and appending its own diagnostics.

Malformed *values* never raise — they are skipped with a diagnostic. Only a
top-level structural failure that leaves nothing to normalize raises
:class:`SeriesError` (carrying a machine-readable ``.code``): the input is not a
mapping, has no ``points`` key, ``points`` is not a list, or a JSON string could
not be parsed. This mirrors the envelope's "missing key fails loudly" stance
while keeping data-quality issues inside ``diagnostics``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from coherence.frames.compat import check_series_frames

# --- machine-readable codes ------------------------------------------------
#
# Structural failures (raised as SeriesError):
CODE_NOT_A_MAPPING = "series_not_a_mapping"
CODE_INVALID_JSON = "series_invalid_json"
CODE_MISSING_POINTS = "series_missing_points"
CODE_POINTS_NOT_A_LIST = "series_points_not_a_list"

# Data-quality issues (appended to Series.diagnostics, never raised):
CODE_INVALID_DOMAIN = "series_invalid_domain"
CODE_POINT_NOT_A_DICT = "series_point_not_a_dict"
CODE_MISSING_ID = "series_missing_id"
CODE_INVALID_INDEX = "series_invalid_index"
CODE_INDEX_MISMATCH = "series_index_mismatch"
CODE_INVALID_VALUES = "series_invalid_values"
CODE_INVALID_VALUE_NAME = "series_invalid_value_name"
CODE_NON_NUMERIC_VALUE = "series_non_numeric_value"
CODE_INVALID_TIMESTAMP = "series_invalid_timestamp"
CODE_INVALID_FRAME = "series_invalid_frame"


class SeriesError(ValueError):
    """Raised when a series is structurally uninterpretable.

    Carries a machine-readable :attr:`code` (one of the ``CODE_*`` constants for
    structural failures) alongside the human-readable message, mirroring
    :class:`coherence.schema.EnvelopeError`, so callers can branch on the
    failure kind rather than parsing strings. This is reserved for top-level
    structure only — malformed *values* are reported through
    :attr:`Series.diagnostics`, not by raising.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class SeriesPoint:
    """One normalized measurement point in a series.

    Attributes:
        id: Human-readable label for the point (never empty after loading).
        index: The point's position in the series (0-based list position).
        timestamp: Optional wall-clock label (ISO string / epoch number) or
            ``None``. Carried through untouched — the signal layer is unitless
            and per-step, so it does no time-axis math.
        values: Well-formed numeric values only, each a ``float``. Names are
            caller-defined; malformed entries were skipped during loading.
        frame: The per-point provenance block (a dict) or ``None`` — always
            explicit, mirroring the envelope's ``frame`` key.
    """

    id: str
    index: int
    values: dict[str, float]
    timestamp: Any | None = None
    frame: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the input-schema dict for this point (round-trips through the loader)."""
        return {
            "id": self.id,
            "index": self.index,
            "timestamp": self.timestamp,
            "values": dict(self.values),
            "frame": dict(self.frame) if isinstance(self.frame, dict) else self.frame,
        }


@dataclass
class Series:
    """A normalized series: an optional domain label, ordered points, diagnostics.

    Attributes:
        domain: Optional producing-dimension label, or ``None``. The signal
            layer never branches on it.
        points: The normalized :class:`SeriesPoint` list, in series order.
        diagnostics: A **mutable** list of ``{"code", "message"}`` dicts
            describing everything skipped or repaired during loading. Left
            appendable on purpose so a later mixed-frame guard can add its own.
    """

    points: list[SeriesPoint]
    domain: str | None = None
    diagnostics: list[dict[str, str]] = field(default_factory=list)

    def field_names(self) -> set[str]:
        """Return the union of every numeric value name present across all points.

        Downstream engines iterate "any numeric series field"; this is the set
        of fields available to iterate. Empty when no point carries a value.
        """
        names: set[str] = set()
        for point in self.points:
            names.update(point.values)
        return names

    def to_dict(self) -> dict[str, Any]:
        """Return the input-schema dict (``domain`` + ``points``), round-trippable.

        Diagnostics are a *loader output*, not part of the input schema, so they
        are intentionally excluded — the result validates as a series and can be
        re-loaded or written out by ``coherence signal collect``.
        """
        return {"domain": self.domain, "points": [p.to_dict() for p in self.points]}


def _is_numeric(value: Any) -> bool:
    """Return ``True`` for a real ``int``/``float`` — but NOT ``bool``.

    ``bool`` is an ``int`` subclass in Python; a boolean flag is not a
    measurement, so it is explicitly excluded (matching the envelope's rule).
    """
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _diag(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _normalize_values(
    raw_values: Any, point_id: str, diagnostics: list[dict[str, str]]
) -> dict[str, float]:
    """Return the well-formed numeric subset of ``raw_values`` as floats.

    Every dropped entry (non-string name, or null / non-numeric / boolean
    value) appends a diagnostic naming the point and the offending field. A
    non-dict ``values`` yields ``{}`` plus one diagnostic.
    """
    if raw_values is None:
        diagnostics.append(
            _diag(CODE_INVALID_VALUES, f"point {point_id!r}: 'values' is missing; treated as empty")
        )
        return {}
    if not isinstance(raw_values, Mapping):
        diagnostics.append(
            _diag(
                CODE_INVALID_VALUES,
                f"point {point_id!r}: 'values' must be an object, got "
                f"{type(raw_values).__name__}; treated as empty",
            )
        )
        return {}

    values: dict[str, float] = {}
    for name, value in raw_values.items():
        if not isinstance(name, str):
            diagnostics.append(
                _diag(
                    CODE_INVALID_VALUE_NAME,
                    f"point {point_id!r}: value name {name!r} is not a string; skipped",
                )
            )
            continue
        if not _is_numeric(value):
            diagnostics.append(
                _diag(
                    CODE_NON_NUMERIC_VALUE,
                    f"point {point_id!r}: value {name!r}={value!r} is not numeric "
                    f"({type(value).__name__}); skipped",
                )
            )
            continue
        values[name] = float(value)
    return values


def _normalize_id(raw: Mapping[str, Any], position: int, diagnostics: list[dict[str, str]]) -> str:
    """Return a non-empty string id, synthesizing ``point-<pos>`` when needed."""
    raw_id = raw.get("id")
    if isinstance(raw_id, str) and raw_id:
        return raw_id
    synthesized = f"point-{position}"
    diagnostics.append(
        _diag(
            CODE_MISSING_ID,
            f"point at position {position}: missing/invalid 'id' ({raw_id!r}); "
            f"synthesized {synthesized!r}",
        )
    )
    return synthesized


def _normalize_index(
    raw: Mapping[str, Any], position: int, point_id: str, diagnostics: list[dict[str, str]]
) -> int:
    """Return the canonical index (the list position), flagging any disagreement."""
    if "index" not in raw:
        return position
    raw_index = raw["index"]
    if isinstance(raw_index, bool) or not isinstance(raw_index, int):
        diagnostics.append(
            _diag(
                CODE_INVALID_INDEX,
                f"point {point_id!r}: 'index' {raw_index!r} is not an int; "
                f"using list position {position}",
            )
        )
    elif raw_index != position:
        diagnostics.append(
            _diag(
                CODE_INDEX_MISMATCH,
                f"point {point_id!r}: declared index {raw_index} != list position "
                f"{position}; using {position}",
            )
        )
    return position


def _normalize_timestamp(
    raw: Mapping[str, Any], point_id: str, diagnostics: list[dict[str, str]]
) -> Any | None:
    """Return a nullable scalar timestamp; non-scalar values become ``None``."""
    timestamp = raw.get("timestamp")
    if timestamp is None:
        return None
    if not isinstance(timestamp, bool) and isinstance(timestamp, (str, int, float)):
        return timestamp
    diagnostics.append(
        _diag(
            CODE_INVALID_TIMESTAMP,
            f"point {point_id!r}: 'timestamp' {timestamp!r} is not a string/number/null; "
            "set to null",
        )
    )
    return None


def _normalize_frame(
    raw: Mapping[str, Any], point_id: str, diagnostics: list[dict[str, str]]
) -> dict[str, Any] | None:
    """Return the per-point frame dict, or ``None`` — always explicit.

    Absent or ``null`` → ``None``. A non-dict, non-null frame is dropped to
    ``None`` with a diagnostic (mirrors the envelope's "frame is a dict or
    None" rule).
    """
    if "frame" not in raw:
        return None
    frame = raw["frame"]
    if frame is None:
        return None
    if isinstance(frame, Mapping):
        return dict(frame)
    diagnostics.append(
        _diag(
            CODE_INVALID_FRAME,
            f"point {point_id!r}: 'frame' must be an object or null, got "
            f"{type(frame).__name__}; set to null",
        )
    )
    return None


def _normalize_point(
    raw: Any, position: int, diagnostics: list[dict[str, str]]
) -> SeriesPoint | None:
    """Normalize one raw points entry, or return ``None`` (with a diagnostic) to skip it."""
    if not isinstance(raw, Mapping):
        diagnostics.append(
            _diag(
                CODE_POINT_NOT_A_DICT,
                f"points[{position}] is not an object ({type(raw).__name__}); skipped",
            )
        )
        return None
    point_id = _normalize_id(raw, position, diagnostics)
    index = _normalize_index(raw, position, point_id, diagnostics)
    values = _normalize_values(raw.get("values"), point_id, diagnostics)
    timestamp = _normalize_timestamp(raw, point_id, diagnostics)
    frame = _normalize_frame(raw, point_id, diagnostics)
    return SeriesPoint(id=point_id, index=index, values=values, timestamp=timestamp, frame=frame)


def _normalize_domain(raw_domain: Any, diagnostics: list[dict[str, str]]) -> str | None:
    """Return the optional domain label, or ``None`` (non-string earns a diagnostic)."""
    if raw_domain is None:
        return None
    if isinstance(raw_domain, str):
        return raw_domain
    diagnostics.append(
        _diag(
            CODE_INVALID_DOMAIN,
            f"'domain' must be a string or absent, got {type(raw_domain).__name__}; "
            "treated as absent",
        )
    )
    return None


def load_series(data: Mapping[str, Any] | str | bytes) -> Series:
    """Load and normalize a raw series into a typed :class:`Series`.

    Accepts either a parsed mapping (the usual case) or a JSON ``str``/``bytes``
    payload, which is parsed first. Returns a :class:`Series` whose ``points``
    are cleaned and whose mutable ``diagnostics`` list records everything that
    was skipped or repaired. Malformed *values* never raise; only top-level
    structural failures do.

    Args:
        data: The raw series — a mapping with a ``points`` list (and optional
            ``domain``), or a JSON string/bytes encoding one.

    Returns:
        A :class:`Series` with normalized points and a diagnostics list.

    Raises:
        SeriesError: The input is not a mapping, is unparseable JSON, lacks a
            ``points`` key, or ``points`` is not a list — carrying a
            machine-readable ``.code``.
    """
    if isinstance(data, (str, bytes)):
        try:
            parsed = json.loads(data)
        except (json.JSONDecodeError, ValueError) as exc:
            raise SeriesError(CODE_INVALID_JSON, f"series is not valid JSON: {exc}") from exc
        data = parsed

    if not isinstance(data, Mapping):
        raise SeriesError(
            CODE_NOT_A_MAPPING,
            f"series must be an object, got {type(data).__name__}",
        )
    if "points" not in data:
        raise SeriesError(CODE_MISSING_POINTS, "series is missing the required 'points' key")
    raw_points = data["points"]
    if not isinstance(raw_points, list):
        raise SeriesError(
            CODE_POINTS_NOT_A_LIST,
            f"series['points'] must be a list, got {type(raw_points).__name__}",
        )

    diagnostics: list[dict[str, str]] = []
    domain = _normalize_domain(data.get("domain"), diagnostics)
    points: list[SeriesPoint] = []
    for position, raw_point in enumerate(raw_points):
        point = _normalize_point(raw_point, position, diagnostics)
        if point is not None:
            points.append(point)
    series = Series(points=points, domain=domain, diagnostics=diagnostics)
    series.diagnostics.extend(check_series_frames(series))
    return series


def series_from_meaning_trend(
    trend_json: Mapping[str, Any], *, domain: str = "meaning"
) -> dict[str, Any]:
    """Convert a ``coherence meaning trend`` result into a series-schema dict.

    This is the source-agnosticism bridge: it flattens each trend point's
    ``meaning_score`` and every subdimension into a single ``values`` bag under
    their caller-defined names, so the resulting dict loads through the *same*
    :func:`load_series` as any hand-written series. The output is the input
    *dict* shape (not a :class:`Series`); pass it to :func:`load_series` to
    normalize.

    The point ``id`` is taken from the trend result's ``paths`` (falling back to
    ``point-<i>`` if a path is missing). Any top-level ``frame`` block on the
    trend result (added by a later frames task) is carried onto *every* point,
    since a meaning-trend series shares one embedding frame across its points;
    when the trend result has no frame, each point's frame is ``null``.

    Args:
        trend_json: The dict returned by :func:`coherence.meaning.trend.trend`.
        domain: The domain label to stamp on the series (defaults to
            ``"meaning"``, matching the producing dimension).

    Returns:
        A series-schema dict (``{"domain", "points"}``) ready for
        :func:`load_series`.
    """
    paths = trend_json.get("paths", [])
    trend_points = trend_json.get("points", [])
    frame = trend_json.get("frame")  # None when the trend result predates the frame block

    points: list[dict[str, Any]] = []
    for i, trend_point in enumerate(trend_points):
        values: dict[str, Any] = {}
        if isinstance(trend_point, Mapping):
            if "meaning_score" in trend_point:
                values["meaning_score"] = trend_point["meaning_score"]
            subdimensions = trend_point.get("subdimensions", {})
            if isinstance(subdimensions, Mapping):
                values.update(subdimensions)
        point_id = str(paths[i]) if i < len(paths) else f"point-{i}"
        points.append(
            {
                "id": point_id,
                "index": i,
                "timestamp": None,
                "values": values,
                "frame": frame,
            }
        )
    return {"domain": domain, "points": points}


__all__ = [
    "Series",
    "SeriesPoint",
    "SeriesError",
    "load_series",
    "series_from_meaning_trend",
    "CODE_NOT_A_MAPPING",
    "CODE_INVALID_JSON",
    "CODE_MISSING_POINTS",
    "CODE_POINTS_NOT_A_LIST",
    "CODE_INVALID_DOMAIN",
    "CODE_POINT_NOT_A_DICT",
    "CODE_MISSING_ID",
    "CODE_INVALID_INDEX",
    "CODE_INDEX_MISMATCH",
    "CODE_INVALID_VALUES",
    "CODE_INVALID_VALUE_NAME",
    "CODE_NON_NUMERIC_VALUE",
    "CODE_INVALID_TIMESTAMP",
    "CODE_INVALID_FRAME",
]
