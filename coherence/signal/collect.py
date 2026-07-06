"""coherence.signal.collect — build a series from N measurement JSONs.

This module is the glue that turns per-artifact measurements (from any domain)
into analyzable signals by extracting numeric values generically, shape-driven
not domain-driven.

The extraction rule:
1. If the measurement has a dict-valued ``scores`` key → use those numeric
   entries (the full-envelope path, for quality/investiture/new domains).
2. Otherwise harvest numeric leaves generically: top-level numeric keys (e.g.
   ``meaning_score``) plus the numeric entries of any top-level dict of
   numbers (e.g. ``subdimensions.consequence`` → field name ``consequence``,
   matching the naming that :func:`coherence.signal.schema.series_from_meaning_trend`
   uses so meaning series stay consistent).

Never branch on the VALUE of ``domain`` — shape determines extraction, not
domain name.

Per output point: ``id`` (source filename or explicit id argument), ``index``
(input position), ``values`` (extracted numerics), ``frame`` (the source
measurement's frame block carried through verbatim, or explicit ``None`` when
absent). Top-level ``domain``: set when all inputs agree on one domain string,
else ``None`` (do not error).

An input with zero extractable numerics raises :class:`SeriesError` with code
``"collect_no_numeric_values"`` so the CLI can map it to exit 1 later.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from coherence.signal.schema import SeriesError


# --- machine-readable error code ---
CODE_NO_NUMERIC_VALUES = "collect_no_numeric_values"


def _is_numeric(value: Any) -> bool:
    """Return ``True`` for a real ``int``/``float`` — but NOT ``bool``.

    Mirrors :func:`coherence.signal.schema._is_numeric`: boolean is not a
    measurement.
    """
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _extract_values(measurement: Mapping[str, Any]) -> dict[str, float]:
    """Extract numeric values from a measurement, shape-driven.

    Rule:
    - If the measurement has a dict-valued ``scores`` key, extract those
      numeric entries (full-envelope path).
    - Otherwise, harvest numeric leaves: top-level numeric keys, plus numeric
      entries of any top-level dict of numbers (for meaning subdimensions).

    Returns an empty dict if nothing is extractable, or raises SeriesError
    (handled by the caller) if the entire measurement has zero numeric values.
    """
    values: dict[str, float] = {}

    # Check for full-envelope ``scores`` dict first
    if "scores" in measurement:
        scores = measurement["scores"]
        if isinstance(scores, Mapping):
            for name, value in scores.items():
                if isinstance(name, str) and _is_numeric(value):
                    values[name] = float(value)
            if values:  # If we found anything in scores, we're done
                return values

    # Otherwise, harvest numeric leaves generically:
    # 1. Top-level numeric keys (e.g., meaning_score)
    for key, value in measurement.items():
        if isinstance(key, str) and _is_numeric(value):
            values[key] = float(value)

    # 2. Numeric entries of any top-level dict of numbers
    # (e.g., subdimensions.consequence)
    for key, value in measurement.items():
        if isinstance(key, str) and isinstance(value, Mapping):
            for subkey, subvalue in value.items():
                if isinstance(subkey, str) and _is_numeric(subvalue):
                    # Use the subkey (e.g., "consequence" from "subdimensions")
                    # to match the naming of series_from_meaning_trend
                    values[subkey] = float(subvalue)

    return values


def _get_domain(measurement: Mapping[str, Any]) -> str | None:
    """Get domain from measurement, or None if missing/non-string."""
    domain = measurement.get("domain")
    if isinstance(domain, str):
        return domain
    return None


def collect(
    measurements: list[Mapping[str, Any]], *, ids: list[str] | None = None
) -> dict[str, Any]:
    """Build a series dict from N measurement JSONs of ANY domain.

    Extracts numeric values generically based on shape (envelope/meaning format),
    not domain name, and validates that at least one input has extractable
    numerics.

    Args:
        measurements: A list of measurement dicts, each from any domain.
        ids: Optional list of point IDs, one per measurement. If omitted,
            points are synthesized as ``"point-<index>"``.

    Returns:
        A series-schema dict with ``domain`` and ``points`` keys, ready for
        :func:`coherence.signal.schema.load_series`.

    Raises:
        SeriesError: If ALL inputs have zero extractable numeric values
            (with code ``"collect_no_numeric_values"``).
        ValueError or IndexError: If ``ids`` length does not match
            ``measurements`` length.
    """
    if ids is not None and len(ids) != len(measurements):
        raise ValueError(
            f"ids list length ({len(ids)}) must match measurements length ({len(measurements)})"
        )

    # Collect all domains to determine series-level domain
    domains_seen: set[str | None] = set()
    points: list[dict[str, Any]] = []

    for index, measurement in enumerate(measurements):
        values = _extract_values(measurement)

        # Accumulate domains (only non-None ones for later check)
        domain = _get_domain(measurement)
        domains_seen.add(domain)

        # Use explicit id or synthesize
        point_id = ids[index] if ids else f"point-{index}"

        # Carry frame from measurement (or None if missing)
        frame = measurement.get("frame")
        if frame is not None and not isinstance(frame, Mapping):
            frame = None

        points.append(
            {
                "id": point_id,
                "index": index,
                "timestamp": None,
                "values": values,
                "frame": frame,
            }
        )

    # After collecting all points, check if ANY have numeric values
    if not any(p["values"] for p in points):
        raise SeriesError(
            CODE_NO_NUMERIC_VALUES,
            "all measurements have zero extractable numeric values",
        )

    # Determine series-level domain: set if ALL inputs agree on one domain string, else None
    # If any input has no domain (None) or domains differ, series domain is None
    non_none_domains = {d for d in domains_seen if d is not None}
    if len(non_none_domains) == 1 and len(domains_seen) == 1:
        # All inputs have the same non-None domain
        series_domain = non_none_domains.pop()
    else:
        # Any domain is missing/None, or domains differ → set series domain to None
        series_domain = None

    return {"domain": series_domain, "points": points}


def collect_files(paths: list[str]) -> dict[str, Any]:
    """Build a series from N JSON files, each containing a measurement.

    Files are collected in order provided. Filenames (without path) are used
    as point IDs.

    Args:
        paths: List of file paths (strings) to measurement JSON files.

    Returns:
        A series-schema dict, ready for :func:`coherence.signal.schema.load_series`.

    Raises:
        SeriesError: If all inputs have zero numeric values.
        FileNotFoundError or json.JSONDecodeError: If a file cannot be read or
            parsed.
    """
    measurements = []
    ids = []

    for path_str in paths:
        path = Path(path_str)
        text = path.read_text(encoding="utf-8")
        measurement = json.loads(text)
        measurements.append(measurement)
        # Use filename (without directory path) as ID
        ids.append(path.name)

    return collect(measurements, ids=ids)


__all__ = ["collect", "collect_files", "SeriesError", "CODE_NO_NUMERIC_VALUES"]
