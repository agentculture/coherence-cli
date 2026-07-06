"""coherence.meaning.score — the Meaning Gradient score engine and JSON contract.

This module is the central assembly point of the Meaning Gradient: it turns an
artifact file into the scored JSON that ``coherence meaning score`` emits. It
wires together the three offline-testable primitives beside it:

* :mod:`coherence.meaning.embed` supplies the artifact + anchor embeddings
  (injectable here as ``embed_fn`` so tests never touch the network).
* :mod:`coherence.meaning.axis` builds each dimension's contrastive axis from
  its anchor vectors and projects the artifact vector onto it.
* :mod:`coherence.meaning.diagnostics` runs the rule-based, always-available
  text checks.

Two design constraints shape the code:

* **One embedding round-trip.** The artifact and *every* anchor line for
  *every* dimension are embedded in a single ``embed_fn`` call, then sliced per
  dimension. The artifact is never re-embedded per subdimension.
* **An open dimension registry.** Subdimensions are computed by iterating
  :data:`coherence.meaning.axis.DIMENSIONS`, so registering a sixth
  subdimension (anchor files + one entry in ``DIMENSIONS``) makes it appear in
  the output with no change to this module's return shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
from numpy.typing import NDArray

from coherence.frames.provenance import build_frame, null_frame
from coherence.meaning import axis as axis_mod
from coherence.meaning.diagnostics import diagnostics
from coherence.meaning.embed import embed_texts

# The global-axis dimension name; it maps to the top-level ``meaning_score``
# rather than into the ``subdimensions`` map.
_GLOBAL_DIMENSION = "meaning"

# --- the additive two-speed envelope keys ----------------------------------
#
# ``meaning`` keeps its pinned v0.5.0 JSON shape (``meaning_score`` /
# ``subdimensions`` / ``diagnostics``) and GAINS only these three additive
# top-level keys — never a reshape (see ``docs/envelope.md``). ``domain`` and
# ``score_type`` are stable module constants; ``frame`` is resolved from the
# runtime embed config at call time via :func:`meaning_frame`.
DOMAIN = "meaning"
# The falsifiability class of the meaning numbers: an embedding-anchor
# projection — gauge-dependent, only comparable within the same frame.
SCORE_TYPE = "model_relative_anchor_defined_projection"

# The anchor set + projection method the meaning engine declares in its frame
# block. These describe *this* engine's gauge; the endpoint/model half of the
# frame is resolved from the environment by :func:`build_frame` at call time.
_ANCHOR_SET = "coherence-cli meaning anchors v1"
_PROJECTION_METHOD = "mean(high) - mean(low), cosine projection"

# The offline-degrade null-frame reason. When the embed endpoint is unreachable
# no measurement frame was established, so the absence is stated explicitly and
# machine-readably — never a fabricated embedding frame.
_OFFLINE_FRAME_CODE = "embed_endpoint_unreachable"
_OFFLINE_FRAME_REASON = (
    "embedding endpoint was unreachable at measurement time; "
    "no model-relative meaning frame could be established"
)

# An embedder maps a batch of texts to one vector per text, order preserved.
# The default is the real HTTP client; tests inject a synthetic offline one.
EmbedFn = Callable[[list[str]], list[list[float]]]


def _read_text(path: str | Path) -> str:
    """Return the UTF-8 text of the artifact at ``path``."""
    return Path(path).read_text(encoding="utf-8")


def measure(
    text: str, *, embed_fn: EmbedFn = embed_texts
) -> tuple[NDArray[np.float64], dict[str, float]]:
    """Embed ``text`` once and project it onto every dimension's axis.

    Returns ``(artifact_vec, raw_scores)`` where ``artifact_vec`` is the
    artifact's embedding as a 1-D float array and ``raw_scores`` maps every name
    in :data:`coherence.meaning.axis.DIMENSIONS` (the global ``meaning`` axis
    plus each subdimension) to its projected score in ``[0, 1]``.

    The artifact and all anchor lines for all dimensions are embedded in a
    single ``embed_fn`` call, then sliced per dimension — the artifact is
    embedded exactly once, never per subdimension. Returning the artifact vector
    alongside the scores lets the compare/trend engines reuse this machinery
    (e.g. for embedding drift) without a second round-trip.

    Args:
        text: The artifact text to score.
        embed_fn: Batch embedder, injectable for offline tests. Defaults to the
            real HTTP :func:`~coherence.meaning.embed.embed_texts`.
    """
    # Iterate the open registry at call time so a newly registered dimension is
    # picked up without touching this module.
    dimensions = tuple(axis_mod.DIMENSIONS)

    # Gather every anchor line for every dimension into one flat batch, tracking
    # the (high, low) span each dimension occupies so we can slice the returned
    # vectors back apart.
    all_lines: list[str] = []
    spans: dict[str, tuple[slice, slice]] = {}
    for dim in dimensions:
        high_lines, low_lines = axis_mod.load_anchors(dim)
        high_span = slice(len(all_lines), len(all_lines) + len(high_lines))
        all_lines.extend(high_lines)
        low_span = slice(len(all_lines), len(all_lines) + len(low_lines))
        all_lines.extend(low_lines)
        spans[dim] = (high_span, low_span)

    # The single embedding round-trip: artifact first, then every anchor line.
    vectors = embed_fn([text, *all_lines])
    artifact_vec = np.asarray(vectors[0], dtype=np.float64)
    anchor_vecs = vectors[1:]

    raw_scores: dict[str, float] = {}
    for dim in dimensions:
        high_span, low_span = spans[dim]
        dim_axis = axis_mod.build_axis(anchor_vecs[high_span], anchor_vecs[low_span])
        raw_scores[dim] = axis_mod.project(artifact_vec, dim_axis)
    return artifact_vec, raw_scores


def meaning_frame() -> dict:
    """Build the meaning engine's frame provenance block for the current run.

    The ``embedding_model``/``embedding_endpoint`` half is resolved from the
    runtime embed config (``COHERENCE_EMBED_URL`` / ``COHERENCE_EMBED_MODEL``)
    *at call time* by :func:`coherence.frames.provenance.build_frame`, so the
    emitted frame follows the environment rather than a cached literal. The
    ``anchor_set``/``projection_method``/``score_type`` half is this engine's
    declared gauge, and ``axes`` are the axis names actually scored — the global
    ``meaning`` axis plus every subdimension, read from
    :data:`coherence.meaning.axis.DIMENSIONS` at call time so a newly registered
    dimension is reflected here too.

    Only meaningful when embeddings actually happened; the offline path uses
    :func:`offline_result` (an explicit null-frame) instead of fabricating one.
    """
    return build_frame(
        anchor_set=_ANCHOR_SET,
        projection_method=_PROJECTION_METHOD,
        score_type=SCORE_TYPE,
        axes=list(axis_mod.DIMENSIONS),
    )


def _score_v050(path: str | Path, *, embed_fn: EmbedFn) -> dict:
    """Return the pinned v0.5.0 meaning result — the three-key clean shape.

    ``{"meaning_score": float, "subdimensions": {...}, "diagnostics": [...]}``,
    with every numeric value in ``[0, 1]``. This is the shape :func:`compare`
    embeds in its ``before``/``after`` blocks (which stay clean v0.5.0 — the
    additive envelope keys live at the *compare* result's top level, not inside
    each side). :func:`score` wraps this core with the three additive keys.
    """
    text = _read_text(path)
    _artifact_vec, raw_scores = measure(text, embed_fn=embed_fn)
    subdimensions = {
        dim: raw_scores[dim] for dim in axis_mod.DIMENSIONS if dim != _GLOBAL_DIMENSION
    }
    return {
        "meaning_score": raw_scores[_GLOBAL_DIMENSION],
        "subdimensions": subdimensions,
        "diagnostics": diagnostics(text),
    }


def score(path: str | Path, *, embed_fn: EmbedFn = embed_texts) -> dict:
    """Score the artifact at ``path`` and return the Meaning Gradient JSON.

    The returned dict keeps its pinned v0.5.0 keys and GAINS exactly three
    additive top-level keys (the two-speed envelope rule; see
    ``docs/envelope.md``)::

        {"meaning_score": float,
         "subdimensions": {"consequence": float, "agency": float,
                           "causality": float, "affordance": float,
                           "future_constraint": float},
         "diagnostics": [{"code": str, "message": str}, ...],
         "domain": "meaning",
         "score_type": "model_relative_anchor_defined_projection",
         "frame": {"embedding_model": ..., "embedding_endpoint": ...,
                   "anchor_set": ..., "projection_method": ...,
                   "score_type": ..., "axes": [...]}}

    Every numeric value is in ``[0, 1]``. The global ``meaning`` dimension maps
    to ``meaning_score``; every other dimension in
    :data:`coherence.meaning.axis.DIMENSIONS` maps into the open
    ``subdimensions`` map (registering a new dimension adds a key here with no
    other change). Diagnostics come from the offline rule engine. ``frame`` is
    resolved from the runtime embed config at call time (see
    :func:`meaning_frame`) — it is built only after the embeddings actually
    succeeded, so it is never fabricated.

    Args:
        path: Filesystem path to the artifact text.
        embed_fn: Batch embedder, injectable for offline tests. Defaults to the
            real HTTP :func:`~coherence.meaning.embed.embed_texts`, which raises
            :class:`~coherence.meaning.EmbedUnavailable` if the endpoint is down.
    """
    result = _score_v050(path, embed_fn=embed_fn)
    result["domain"] = DOMAIN
    result["score_type"] = SCORE_TYPE
    result["frame"] = meaning_frame()
    return result


def offline_result(path: str | Path) -> dict:
    """Return the offline-degrade meaning result when embeddings are unavailable.

    This is the always-available offline-diagnostics path: it never embeds, so
    it succeeds when the embedding endpoint is down (unlike :func:`score`, which
    raises :class:`~coherence.meaning.EmbedUnavailable` and drives the CLI's
    exit-2 path). No ``meaning_score``/``subdimensions`` can be computed without
    embeddings, so they are honestly absent; the rule diagnostics still run, and
    ``frame`` is an explicit :func:`coherence.schema.null_frame` carrying the
    machine-readable reason ``embed_endpoint_unreachable`` — never a fabricated
    embedding frame::

        {"domain": "meaning",
         "score_type": "model_relative_anchor_defined_projection",
         "diagnostics": [{"code": str, "message": str}, ...],
         "frame": {"available": False, "code": "embed_endpoint_unreachable",
                   "reason": str}}

    Consumers that surface partial availability (e.g. the multi-domain assess
    report) use this to list meaning as unavailable-with-a-reason while still
    showing what the offline rules could flag.
    """
    return {
        "domain": DOMAIN,
        "score_type": SCORE_TYPE,
        "diagnostics": diagnostics(_read_text(path)),
        "frame": null_frame(_OFFLINE_FRAME_REASON, code=_OFFLINE_FRAME_CODE),
    }


def diagnostics_only(path: str | Path) -> list[dict]:
    """Return just the offline diagnostics for the artifact at ``path``.

    This never embeds, so it succeeds even when the embedding endpoint is down —
    the always-available degrade path for when :func:`score` would raise
    :class:`~coherence.meaning.EmbedUnavailable`.
    """
    return diagnostics(_read_text(path))


__all__ = [
    "score",
    "offline_result",
    "meaning_frame",
    "diagnostics_only",
    "measure",
    "EmbedFn",
    "DOMAIN",
    "SCORE_TYPE",
]
