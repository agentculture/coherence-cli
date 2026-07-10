"""Builder for the frame provenance block attached to embedding-derived
measurements.

This repo's spec calls embedding-derived scores "model-relative,
anchor-defined semantic measurements" (see ``docs/envelope.md`` and the
frames-domain requirement in
``docs/specs/2026-07-06-coherence-cli-ships-as-a-five-domain-coherence-eng.md``):
a number like ``meaning_score: 0.62`` is meaningless without knowing *which*
semantic coordinate frame produced it. The frame block is that declared gauge:

    {"embedding_model": ..., "embedding_endpoint": ...,
     "anchor_set": ..., "axis": ... | "axes": [...],
     "projection_method": ..., "score_type": ...}

``embedding_model``/``embedding_endpoint`` are resolved from the runtime embed
config — the same ``COHERENCE_EMBED_URL``/``COHERENCE_EMBED_MODEL``
environment variables (and defaults) that :mod:`coherence.meaning.embed` uses
for the actual embeddings request — read *at call time*, not cached at import.
This module reuses that resolution logic directly rather than duplicating the
default literals or the env-var lookup: a change to how ``embed.py`` resolves
its config (e.g. trimming, additional fallback) is automatically reflected
here too.

``anchor_set``/``axis``/``axes``/``projection_method``/``score_type`` are
supplied by the caller (the meaning engine, investiture, etc. know their own
anchor set and projection method); this module only assembles the block and
resolves the parts that come from the environment.

Absent provenance is handled by re-exporting
:func:`coherence.schema.null_frame` — the canonical "explicit null-frame with
a machine-readable reason" representation — rather than reinventing it here.
"""

from __future__ import annotations

from typing import Any

# Reuse the exact runtime resolution logic from coherence.meaning.embed (the
# same functions the real embeddings request uses) instead of duplicating the
# COHERENCE_EMBED_URL/COHERENCE_EMBED_MODEL lookup or their default literals.
from coherence.meaning.embed import _embed_model as _resolve_embed_model
from coherence.meaning.embed import _embed_url as _resolve_embed_url

# Re-exported, not reinvented: coherence.schema already defines the canonical
# null-frame shape for explicitly absent provenance.
from coherence.schema import null_frame

__all__ = ["build_frame", "null_frame"]


def _require_non_empty_str(name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty str, got {value!r}")


def build_frame(
    *,
    anchor_set: str,
    projection_method: str,
    score_type: str,
    axis: str | None = None,
    axes: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble the frame provenance block for an embedding-derived measurement.

    ``embedding_model``/``embedding_endpoint`` are resolved from the runtime
    embed config at call time (see module docstring); every other field is
    supplied by the caller, which knows its own anchor set, axis/axes,
    projection method, and score type.

    Args:
        anchor_set: Name of the anchor set that defined the projection (e.g.
            ``"meaning-v1"``). Non-empty str.
        projection_method: Name of the projection method (e.g.
            ``"contrastive_axis"``). Non-empty str.
        score_type: The falsifiability class of the resulting score (e.g.
            ``"model_relative_anchor_defined_projection"``), mirroring
            ``coherence.schema``'s ``score_type`` field. Non-empty str.
        axis: Name of the single semantic axis measured, when there is
            exactly one (e.g. ``"valence"``). Mutually exclusive with
            ``axes``.
        axes: Names of multiple semantic axes measured, when there is more
            than one. Mutually exclusive with ``axis``. Must be non-empty
            when provided; copied defensively so mutating the caller's list
            afterwards does not affect the returned frame.

    Returns:
        A frame dict with keys ``embedding_model``, ``embedding_endpoint``,
        ``anchor_set``, ``projection_method``, ``score_type``, and exactly one
        of ``axis``/``axes`` when given (neither key is present when neither
        is supplied). Valid as the ``frame`` value of the shared measurement
        envelope (:func:`coherence.schema.build_envelope`).

    Raises:
        ValueError: ``anchor_set``/``projection_method``/``score_type`` is
            empty or not a str; both ``axis`` and ``axes`` are given; or
            ``axes`` is given but empty.
    """
    _require_non_empty_str("anchor_set", anchor_set)
    _require_non_empty_str("projection_method", projection_method)
    _require_non_empty_str("score_type", score_type)
    if axis is not None and axes is not None:
        raise ValueError("pass either axis or axes, not both")
    if axes is not None and not axes:
        raise ValueError("axes must be a non-empty list when provided")

    frame: dict[str, Any] = {
        "embedding_model": _resolve_embed_model(),
        "embedding_endpoint": _resolve_embed_url(),
        "anchor_set": anchor_set,
        "projection_method": projection_method,
        "score_type": score_type,
    }
    if axes is not None:
        frame["axes"] = list(axes)
    elif axis is not None:
        frame["axis"] = axis
    return frame
