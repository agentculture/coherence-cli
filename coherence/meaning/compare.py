"""coherence.meaning.compare — two-point Meaning Gradient deltas.

The compare engine scores two artifact versions — a ``before`` and an
``after`` — and reports how much meaning moved between them. It is the
smallest step above the single-file :mod:`coherence.meaning.score` engine: no
trend, no history, just the signed change from one snapshot to the next.

Design constraints (mirroring ``score``):

* **Reuse, don't reimplement.** All scoring goes through
  :func:`coherence.meaning.score.score`; this module only subtracts. The same
  ``embed_fn`` injection seam is threaded through to both scored files so tests
  can drive it fully offline with a synthetic embedder.
* **Signed, after-minus-before deltas.** ``delta = after - before`` for the
  global ``meaning_score`` and for every subdimension, so a positive delta
  always means the ``after`` artifact *gained* meaning on that dimension.
* **An open subdimension registry.** Deltas are computed by iterating the
  subdimensions the score engine actually returned, so registering a sixth
  subdimension (see :data:`coherence.meaning.axis.DIMENSIONS`) flows through to
  the delta map with no change here.
"""

from __future__ import annotations

from pathlib import Path

from coherence.meaning.embed import embed_texts
from coherence.meaning.score import DOMAIN, SCORE_TYPE, EmbedFn, _score_v050, meaning_frame


def compare(
    before: str | Path,
    after: str | Path,
    *,
    embed_fn: EmbedFn = embed_texts,
) -> dict:
    """Score two artifacts and return their before/after scores plus the delta.

    The returned dict keeps its pinned v0.5.0 keys and GAINS exactly three
    additive top-level keys (the two-speed envelope rule; see
    ``docs/envelope.md``)::

        {"before": <clean v0.5.0 score dict>,
         "after":  <clean v0.5.0 score dict>,
         "delta":  {"meaning_score": float,
                    "subdimensions": {"consequence": float, "agency": float,
                                      "causality": float, "affordance": float,
                                      "future_constraint": float}},
         "domain": "meaning",
         "score_type": "model_relative_anchor_defined_projection",
         "frame": {...}}

    ``delta`` is ``after - before`` for ``meaning_score`` and for every
    subdimension the score engine returns (signed; positive means the ``after``
    artifact gained meaning on that dimension). Comparing a file against itself
    yields all-zero deltas.

    The ``before``/``after`` blocks stay the clean v0.5.0 shape (``meaning_score``
    / ``subdimensions`` / ``diagnostics``) — the envelope keys live at *one*
    top level for the whole comparison, since both sides were measured under the
    same runtime embed config, so there is a single shared :func:`frame` block
    rather than a duplicate per side.

    Args:
        before: Filesystem path to the earlier artifact version.
        after: Filesystem path to the later artifact version.
        embed_fn: Batch embedder, injectable for offline tests. Threaded
            unchanged into the score engine for *both* files. Defaults to the
            real HTTP :func:`~coherence.meaning.embed.embed_texts`.
    """
    before_score = _score_v050(before, embed_fn=embed_fn)
    after_score = _score_v050(after, embed_fn=embed_fn)
    return {
        "before": before_score,
        "after": after_score,
        "delta": _delta(before_score, after_score),
        "domain": DOMAIN,
        "score_type": SCORE_TYPE,
        "frame": meaning_frame(),
    }


def _delta(before_score: dict, after_score: dict) -> dict:
    """Return the signed ``after - before`` delta for meaning_score + subdims.

    The subdimension delta map is keyed by exactly the subdimensions present in
    ``after_score`` (the open registry), each value being
    ``after[sub] - before[sub]``.
    """
    before_subs = before_score["subdimensions"]
    after_subs = after_score["subdimensions"]
    subdimensions = {
        name: after_value - before_subs[name] for name, after_value in after_subs.items()
    }
    return {
        "meaning_score": after_score["meaning_score"] - before_score["meaning_score"],
        "subdimensions": subdimensions,
    }


__all__ = ["compare"]
