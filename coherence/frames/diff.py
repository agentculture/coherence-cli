"""coherence.frames.diff — are two measurements frame-COMPARABLE (same gauge)?

``coherence frames diff <a.json> <b.json>`` (CLI wiring lands in task t16)
answers the question the mixed-frame guard (:mod:`coherence.frames.compat`)
exists to prevent agents from ignoring: two embedding-derived scores are only
safely comparable when the semantic coordinate frame that produced them
matches. This module is that comparison, as a pure function over two
already-loaded measurement dicts.

What counts as "the same gauge" — a documented call
-----------------------------------------------------
:data:`IDENTITY_FIELDS` — ``embedding_model``, ``embedding_endpoint``,
``anchor_set``, ``projection_method`` — are the fields that determine whether
two frames measure with the *same instrument*: same embedding model, same
serving endpoint, same anchor set, same projection method. A difference in any
of these means the two numbers were produced by genuinely different
instruments and are not comparable; ``result["comparable"]`` is ``False`` and
every differing field is named in ``result["differing_fields"]`` with both
values.

``axis``/``axes`` and ``score_type`` are reported too, but — this module's
documented design call — they do NOT by themselves flip ``comparable`` to
``False``. Two measurements can share the exact same gauge while projecting a
different semantic axis through it (e.g. ``valence`` vs ``arousal``) or
declaring a different falsifiability class; that is a meaningful difference
worth surfacing; but it is not the "wrong instrument" failure identity-field
mismatches are. These are reported separately in
``result["soft_differences"]``, and folded into a softer verdict message when
they are the only differences found (``comparable`` stays ``True``).

Absent frames get their own two codes, not a single generic "not comparable":

* :data:`CODE_NO_PROVENANCE_TO_COMPARE` — neither measurement carries usable
  frame provenance (no ``"frame"`` key, ``frame: null``, or an explicit
  null-frame dict on both sides). There is nothing to compare, so this is
  distinct from an actual identity mismatch.
* :data:`CODE_ASYMMETRIC_FRAME_PRESENCE` — exactly one side carries usable
  frame provenance and the other does not. This is its own failure mode
  (an apples-to-nothing comparison), not folded into the mismatch code.

Fully offline: no network, no embeddings call.
"""

from __future__ import annotations

from typing import Any, Mapping

# --- the "same gauge" identity fields (see module docstring) ----------------
IDENTITY_FIELDS: tuple[str, ...] = (
    "embedding_model",
    "embedding_endpoint",
    "anchor_set",
    "projection_method",
)

# Fields reported but not gauge-defining on their own (documented call above).
SOFT_FIELDS: tuple[str, ...] = ("axis", "score_type")

# --- machine-readable verdict codes -----------------------------------------
CODE_FRAMES_COMPARABLE = "frames_comparable"
CODE_FRAME_IDENTITY_MISMATCH = "frame_identity_mismatch"
CODE_NO_PROVENANCE_TO_COMPARE = "no_provenance_to_compare"
CODE_ASYMMETRIC_FRAME_PRESENCE = "asymmetric_frame_presence"


def _is_null_frame(frame: Mapping[str, Any]) -> bool:
    """Return True for the canonical null-frame shape (``available: False``).

    Mirrors :func:`coherence.frames.inspect._is_null_frame`; duplicated here
    (rather than imported) since the two modules are independently owned and
    this is a three-line check on a stable, documented shape
    (:func:`coherence.schema.null_frame`).
    """
    return frame.get("available") is False


def usable_frame(measurement: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Return ``measurement``'s frame dict if it carries usable identity, else None.

    "Usable" means: the ``"frame"`` key is present, its value is a dict, and
    that dict is not an explicit null-frame marker. Every other shape (no key,
    ``null``, a non-dict value, or a null-frame dict) has nothing to compare
    and is treated as absent for gauge-comparison purposes.
    """
    if "frame" not in measurement:
        return None
    frame = measurement["frame"]
    if frame is None or not isinstance(frame, Mapping):
        return None
    if _is_null_frame(frame):
        return None
    return frame


def frame_identity(frame: Mapping[str, Any] | None) -> tuple[Any, ...] | None:
    """Return a hashable identity tuple over :data:`IDENTITY_FIELDS`, or None.

    ``None`` means ``frame`` carries no usable gauge identity (absent, null,
    non-dict, or an explicit null-frame). Reused by
    :mod:`coherence.frames.compat` so the mixed-frame guard's notion of
    "same frame" stays identical to this module's.
    """
    if frame is None or not isinstance(frame, Mapping) or _is_null_frame(frame):
        return None
    return tuple(frame.get(name) for name in IDENTITY_FIELDS)


def _axis_identity(frame: Mapping[str, Any]) -> Any:
    """Return a comparable value for ``frame``'s axis/axes, or ``None``."""
    if "axis" in frame:
        return frame.get("axis")
    axes = frame.get("axes")
    if isinstance(axes, list):
        return tuple(axes)
    return None


def _field_diffs(
    frame_a: Mapping[str, Any], frame_b: Mapping[str, Any], fields: tuple[str, ...]
) -> dict[str, dict[str, Any]]:
    diffs: dict[str, dict[str, Any]] = {}
    for name in fields:
        va, vb = frame_a.get(name), frame_b.get(name)
        if va != vb:
            diffs[name] = {"a": va, "b": vb}
    return diffs


def diff_frames(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]:
    """Compare two measurements' frames for gauge-comparability.

    Args:
        a: The first already-loaded measurement dict.
        b: The second already-loaded measurement dict.

    Returns:
        A dict with keys:

        * ``comparable`` — ``bool``. ``True`` only when both sides carry
          usable frame provenance and every :data:`IDENTITY_FIELDS` value
          matches.
        * ``code`` — one of :data:`CODE_FRAMES_COMPARABLE`,
          :data:`CODE_FRAME_IDENTITY_MISMATCH`,
          :data:`CODE_NO_PROVENANCE_TO_COMPARE`,
          :data:`CODE_ASYMMETRIC_FRAME_PRESENCE`.
        * ``message`` — human-readable summary of the verdict.
        * ``differing_fields`` — ``{field_name: {"a": ..., "b": ...}}`` for
          every :data:`IDENTITY_FIELDS` mismatch (drives ``comparable``);
          also carries a single ``"frame"`` entry when one side is absent and
          the other present.
        * ``soft_differences`` — same shape, for ``axis``/``score_type``
          mismatches; never blocks ``comparable``.
        * ``frame_a`` / ``frame_b`` — the usable frame dicts compared (a
          defensive copy each), or ``None`` when that side had no usable
          provenance.
    """
    frame_a = usable_frame(a)
    frame_b = usable_frame(b)

    if frame_a is None and frame_b is None:
        return {
            "comparable": False,
            "code": CODE_NO_PROVENANCE_TO_COMPARE,
            "message": "neither measurement carries frame provenance; no provenance to compare",
            "differing_fields": {},
            "soft_differences": {},
            "frame_a": None,
            "frame_b": None,
        }

    if frame_a is None or frame_b is None:
        missing_side = "a" if frame_a is None else "b"
        return {
            "comparable": False,
            "code": CODE_ASYMMETRIC_FRAME_PRESENCE,
            "message": (
                f"measurement {missing_side} carries no frame provenance while the "
                "other does; not comparable"
            ),
            "differing_fields": {"frame": {"a": frame_a, "b": frame_b}},
            "soft_differences": {},
            "frame_a": dict(frame_a) if frame_a is not None else None,
            "frame_b": dict(frame_b) if frame_b is not None else None,
        }

    differing = _field_diffs(frame_a, frame_b, IDENTITY_FIELDS)

    soft: dict[str, dict[str, Any]] = {}
    axis_a, axis_b = _axis_identity(frame_a), _axis_identity(frame_b)
    if axis_a != axis_b:
        soft["axis"] = {"a": axis_a, "b": axis_b}
    score_type_a, score_type_b = frame_a.get("score_type"), frame_b.get("score_type")
    if score_type_a != score_type_b:
        soft["score_type"] = {"a": score_type_a, "b": score_type_b}

    if differing:
        return {
            "comparable": False,
            "code": CODE_FRAME_IDENTITY_MISMATCH,
            "message": f"frames differ in: {', '.join(sorted(differing))}; not comparable",
            "differing_fields": differing,
            "soft_differences": soft,
            "frame_a": dict(frame_a),
            "frame_b": dict(frame_b),
        }

    message = "frames share the same gauge; comparable"
    if soft:
        message += f" (though they differ in: {', '.join(sorted(soft))})"
    return {
        "comparable": True,
        "code": CODE_FRAMES_COMPARABLE,
        "message": message,
        "differing_fields": {},
        "soft_differences": soft,
        "frame_a": dict(frame_a),
        "frame_b": dict(frame_b),
    }


__all__ = [
    "diff_frames",
    "usable_frame",
    "frame_identity",
    "IDENTITY_FIELDS",
    "SOFT_FIELDS",
    "CODE_FRAMES_COMPARABLE",
    "CODE_FRAME_IDENTITY_MISMATCH",
    "CODE_NO_PROVENANCE_TO_COMPARE",
    "CODE_ASYMMETRIC_FRAME_PRESENCE",
]
