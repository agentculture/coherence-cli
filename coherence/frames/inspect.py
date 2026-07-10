"""coherence.frames.inspect — report the frame that produced a measurement.

``coherence frames inspect <measurement.json>`` (CLI wiring lands in task t16)
answers one question: *which semantic coordinate frame produced this
measurement's scores, and is its provenance complete?* This module is the
engine behind that question — a pure function over an already-loaded
measurement dict, no I/O, no network.

Three distinguishable outcomes, reported in ``result["status"]``:

* ``"complete"`` — ``measurement["frame"]`` is a dict carrying every field
  :func:`coherence.frames.provenance.build_frame` emits: ``embedding_model``,
  ``embedding_endpoint``, ``anchor_set``, ``axis`` or ``axes``,
  ``projection_method``, ``score_type`` — each present and non-empty.
* ``"partial"`` — ``measurement["frame"]`` is a dict, but one or more of those
  fields is missing/empty; ``result["missing_fields"]`` names them.
* ``"absent"`` — there is nothing to report: the measurement predates the
  frame block entirely (no ``"frame"`` key at all — the exact shape of a
  v0.5.0-era :func:`coherence.meaning.score.score` output), ``frame`` is
  explicitly ``null``, or ``frame`` is a non-dict value that cannot carry
  provenance. This also covers an explicit null-frame dict
  (:func:`coherence.schema.null_frame`'s
  ``{"available": False, "code", "reason"}`` shape) — in that case its
  machine-readable ``reason``/``code`` are surfaced on the result directly, not
  just buried in a diagnostic message.

Absence is never an error. Every branch below returns a normal dict result
with at least one ``{"code", "message"}`` diagnostic explaining what was (or
wasn't) found — this is deliberate: a v0.5.0-era measurement or a measurement
whose embed endpoint was down at capture time is an entirely ordinary input,
and the CLI built on top of this (task t16) is expected to exit ``0`` on it,
never ``1``/``2``. Reserve raising for genuinely malformed *input* (not a
mapping at all), which is a caller bug rather than a data-quality signal.
"""

from __future__ import annotations

from typing import Any, Mapping

# --- machine-readable status values -----------------------------------------
STATUS_COMPLETE = "complete"
STATUS_PARTIAL = "partial"
STATUS_ABSENT = "absent"

# --- machine-readable diagnostic codes --------------------------------------
CODE_FRAME_ABSENT = "frame_absent"
CODE_FRAME_NULL_FRAME = "frame_null_frame"
CODE_FRAME_PARTIAL = "frame_partial"

# The scalar identity fields every complete frame must carry (see
# coherence.frames.provenance.build_frame). ``axis``/``axes`` is handled
# separately below since exactly one of the two, not a fixed key name, is
# required.
_REQUIRED_SCALAR_FIELDS: tuple[str, ...] = (
    "embedding_model",
    "embedding_endpoint",
    "anchor_set",
    "projection_method",
    "score_type",
)


def _diag(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _is_null_frame(frame: Mapping[str, Any]) -> bool:
    """Return True for the canonical null-frame shape (``available: False``).

    :func:`coherence.schema.null_frame` always sets ``available`` to ``False``
    on the dict it builds; a real frame from
    :func:`coherence.frames.provenance.build_frame` never carries an
    ``available`` key at all, so this check cannot false-positive on a
    genuine (even if partial) frame.
    """
    return frame.get("available") is False


def _has_axis_identity(frame: Mapping[str, Any]) -> bool:
    """Return True when ``frame`` carries a usable ``axis`` or ``axes`` value."""
    axis = frame.get("axis")
    if isinstance(axis, str) and axis:
        return True
    axes = frame.get("axes")
    return isinstance(axes, list) and len(axes) > 0 and all(isinstance(a, str) and a for a in axes)


def _missing_frame_fields(frame: Mapping[str, Any]) -> list[str]:
    """Return the names of every required field missing/empty on ``frame``.

    Scalar fields are named individually; ``axis``/``axes`` is reported as the
    single combined name ``"axis/axes"`` when neither is usably present,
    matching how the two are documented as one requirement (exactly one of
    the two, not both keys).
    """
    missing = [
        name
        for name in _REQUIRED_SCALAR_FIELDS
        if not isinstance(frame.get(name), str) or not frame.get(name)
    ]
    if not _has_axis_identity(frame):
        missing.append("axis/axes")
    return missing


def _absent_result(
    diagnostic: dict[str, str], *, reason: str | None = None, code: str | None = None
) -> dict[str, Any]:
    return {
        "status": STATUS_ABSENT,
        "frame": None,
        "missing_fields": [],
        "reason": reason,
        "code": code,
        "diagnostics": [diagnostic],
    }


def inspect_measurement(measurement: Mapping[str, Any]) -> dict[str, Any]:
    """Report the frame that produced ``measurement`` and its provenance state.

    Args:
        measurement: An already-loaded measurement dict — either the shared
            envelope shape (:mod:`coherence.schema`, with a ``"frame"`` key
            always present) or a pre-envelope shape that may have no
            ``"frame"`` key at all (e.g. a v0.5.0-era
            :func:`coherence.meaning.score.score` result).

    Returns:
        A dict with keys:

        * ``status`` — one of :data:`STATUS_COMPLETE`, :data:`STATUS_PARTIAL`,
          :data:`STATUS_ABSENT`.
        * ``frame`` — the frame dict when present (a defensive copy), else
          ``None``.
        * ``missing_fields`` — names of fields missing from a partial frame;
          ``[]`` otherwise.
        * ``reason`` — the null-frame's human-readable reason, when the frame
          is an explicit null-frame dict; ``None`` otherwise.
        * ``code`` — the null-frame's machine-readable code, under the same
          condition; ``None`` otherwise.
        * ``diagnostics`` — a list of ``{"code", "message"}`` dicts, ``[]``
          only when the frame is complete.

    Raises:
        TypeError: ``measurement`` is not a mapping. This is the only failure
            mode that raises — every provenance state described above (even a
            fully absent frame) is a normal, non-raising result.
    """
    if not isinstance(measurement, Mapping):
        raise TypeError(f"measurement must be a mapping, got {type(measurement).__name__}")

    if "frame" not in measurement:
        return _absent_result(
            _diag(
                CODE_FRAME_ABSENT,
                "measurement has no 'frame' key at all (pre-frame / v0.5.0-era "
                "measurement shape); no provenance to report",
            )
        )

    frame = measurement["frame"]

    if frame is None:
        return _absent_result(
            _diag(CODE_FRAME_ABSENT, "measurement['frame'] is null; no provenance available")
        )

    if not isinstance(frame, Mapping):
        return _absent_result(
            _diag(
                CODE_FRAME_ABSENT,
                f"measurement['frame'] must be an object or null, got "
                f"{type(frame).__name__}; treated as absent",
            )
        )

    if _is_null_frame(frame):
        reason = frame.get("reason") if isinstance(frame.get("reason"), str) else None
        null_code = frame.get("code") if isinstance(frame.get("code"), str) else None
        message = "measurement carries an explicit null-frame (no provenance available)"
        if reason:
            message += f": {reason}"
        return _absent_result(_diag(CODE_FRAME_NULL_FRAME, message), reason=reason, code=null_code)

    missing = _missing_frame_fields(frame)
    if missing:
        return {
            "status": STATUS_PARTIAL,
            "frame": dict(frame),
            "missing_fields": missing,
            "reason": None,
            "code": None,
            "diagnostics": [
                _diag(
                    CODE_FRAME_PARTIAL,
                    f"frame is missing required field(s): {', '.join(missing)}",
                )
            ],
        }

    return {
        "status": STATUS_COMPLETE,
        "frame": dict(frame),
        "missing_fields": [],
        "reason": None,
        "code": None,
        "diagnostics": [],
    }


__all__ = [
    "inspect_measurement",
    "STATUS_COMPLETE",
    "STATUS_PARTIAL",
    "STATUS_ABSENT",
    "CODE_FRAME_ABSENT",
    "CODE_FRAME_NULL_FRAME",
    "CODE_FRAME_PARTIAL",
]
