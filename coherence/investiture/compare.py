"""coherence.investiture.compare — two-point investiture delta engine.

The compare engine scores two artifact versions — a ``before`` and an
``after`` — and reports how much estimated investiture moved between them. It
is the smallest step above the single-file :mod:`coherence.investiture.score`
engine: no trace, no history, just the signed change from one snapshot to the
next (investiture *trace* — evidence of persistence/propagation/behavioral
effect — is explicitly deferred; see issue #8).

Design constraints (mirroring :mod:`coherence.meaning.compare` and
:mod:`coherence.quality.compare`):

* **Reuse, don't reimplement.** All scoring goes through
  :func:`coherence.investiture.score.score`; this module only subtracts. The
  same ``embed_fn`` injection seam is threaded through to both scored files, so
  tests can drive it fully offline with a synthetic embedder, and the shared
  :class:`~coherence.meaning.EmbedUnavailable` propagates unchanged when the
  embed endpoint is down.
* **``before``/``after`` are the FULL score results, envelope and all.**
  Unlike :mod:`coherence.meaning.compare` (which strips its pinned v0.5.0
  shape down to a clean core per side, because meaning has a legacy shape to
  protect), investiture is a NEW noun with no legacy shape — so, like
  :mod:`coherence.quality.compare`, each side is exactly what
  :func:`coherence.investiture.score.score` returns: a fully self-contained,
  independently-``validate_envelope``-able measurement, frame included. There
  is deliberately no *second*, top-level frame/domain/score_type for the
  comparison as a whole — both sides already carry their own (identical, since
  both were measured under the same runtime embed config), so duplicating them
  again at ``compare``'s own top level would be redundant.
* **Signed, after-minus-before deltas.** ``delta = after - before`` for
  ``investiture_score`` and for each of the four NUMERIC components, so a
  positive delta always means the ``after`` artifact gained investiture on
  that dimension. The three unmeasured components (``persistence_signal`` /
  ``integration_signal`` / ``behavioral_effect``) have no delta to report —
  they are absent, not zero, in both ``before`` and ``after``, so subtracting
  them would fabricate a number for something that was never measured.
"""

from __future__ import annotations

from pathlib import Path

from coherence.investiture.score import _NUMERIC_COMPONENTS, EmbedFn, score
from coherence.meaning.embed import embed_texts

# Reused (not re-declared) from coherence.investiture.score: the four numeric
# components a delta can meaningfully be computed for. Importing the shared
# tuple rather than hardcoding a second copy means a future rename/reorder/
# extension of score.py's component names is automatically reflected here,
# instead of silently drifting out of sync (mirroring
# coherence.meaning.compare's "reuse, don't reimplement" convention). The
# unmeasured triplet (persistence_signal/integration_signal/behavioral_effect)
# is intentionally excluded — see module docstring.


def compare(
    before: str | Path,
    after: str | Path,
    *,
    embed_fn: EmbedFn = embed_texts,
) -> dict:
    """Score two artifacts and return their before/after scores plus the delta.

    Returns exactly three top-level keys::

        {"before": <coherence.investiture.score.score(before) dict>,
         "after":  <coherence.investiture.score.score(after) dict>,
         "delta":  {"investiture_score": float,
                    "components": {"meaning_density": float,
                                   "agency_coupling": float,
                                   "future_constraint": float,
                                   "affordance": float}}}

    ``delta`` is ``after - before`` for ``investiture_score`` and for each
    numeric component (signed; positive means the ``after`` artifact gained
    investiture on that dimension). Comparing a file against itself yields
    all-zero deltas.

    Args:
        before: Filesystem path to the earlier artifact version.
        after: Filesystem path to the later artifact version.
        embed_fn: Batch embedder, injectable for offline tests. Threaded
            unchanged into :func:`coherence.investiture.score.score` for
            *both* files. Defaults to the real HTTP
            :func:`~coherence.meaning.embed.embed_texts`, which raises
            :class:`~coherence.meaning.EmbedUnavailable` if the embedding
            endpoint is down — this function does not catch that exception,
            so it propagates unchanged.
    """
    before_score = score(before, embed_fn=embed_fn)
    after_score = score(after, embed_fn=embed_fn)
    return {
        "before": before_score,
        "after": after_score,
        "delta": _delta(before_score, after_score),
    }


def _delta(before_score: dict, after_score: dict) -> dict:
    """Return the signed ``after - before`` delta for investiture_score + components."""
    before_components = before_score["components"]
    after_components = after_score["components"]
    component_deltas = {
        name: after_components[name] - before_components[name] for name in _NUMERIC_COMPONENTS
    }
    return {
        "investiture_score": after_score["investiture_score"] - before_score["investiture_score"],
        "components": component_deltas,
    }


__all__ = ["compare"]
