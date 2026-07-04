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
from coherence.meaning.score import EmbedFn, score


def compare(
    before: str | Path,
    after: str | Path,
    *,
    embed_fn: EmbedFn = embed_texts,
) -> dict:
    """Score two artifacts and return their before/after scores plus the delta.

    The returned dict has exactly three keys::

        {"before": <score(before) dict>,
         "after":  <score(after) dict>,
         "delta":  {"meaning_score": float,
                    "subdimensions": {"consequence": float, "agency": float,
                                      "causality": float, "affordance": float,
                                      "future_constraint": float}}}

    ``delta`` is ``after - before`` for ``meaning_score`` and for every
    subdimension the score engine returns (signed; positive means the ``after``
    artifact gained meaning on that dimension). Comparing a file against itself
    yields all-zero deltas.

    Args:
        before: Filesystem path to the earlier artifact version.
        after: Filesystem path to the later artifact version.
        embed_fn: Batch embedder, injectable for offline tests. Threaded
            unchanged into :func:`~coherence.meaning.score.score` for *both*
            files. Defaults to the real HTTP
            :func:`~coherence.meaning.embed.embed_texts`.
    """
    before_score = score(before, embed_fn=embed_fn)
    after_score = score(after, embed_fn=embed_fn)
    return {
        "before": before_score,
        "after": after_score,
        "delta": _delta(before_score, after_score),
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
