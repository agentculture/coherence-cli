"""coherence.quality.compare — two-point quality delta engine.

The compare engine scores two artifact versions — a ``before`` and an ``after``
— and reports how much quality changed between them. It is the smallest step
above the single-file :mod:`coherence.quality.score` engine: no trend, no
history, just the signed change from one snapshot to the next.

Design constraints (mirroring ``score``):

* **Reuse, don't reimplement.** All scoring goes through
  :func:`coherence.quality.score.score_text`; this module only subtracts.
* **Signed, after-minus-before deltas.** ``delta = after - before`` for every
  component and confidence value, so a positive delta always means the ``after``
  artifact *gained* quality on that dimension.
* **An open component registry.** Deltas are computed by iterating the
  components the score engine actually returned (from the ``scores`` map), so
  registering a new component flows through to the delta map with no change
  here.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from coherence.quality.score import score_text


def compare(
    before: str | Path,
    after: str | Path,
    *,
    reference_date: date | None = None,
) -> dict:
    """Score two artifacts and return their before/after scores plus the delta.

    The returned dict has exactly three keys::

        {"before": <score_text(before) dict>,
         "after":  <score_text(after) dict>,
         "delta":  {"freshness": float, "provenance": float, "fidelity": float,
                    "freshness_confidence": float, "provenance_confidence": float,
                    "fidelity_confidence": float}}

    ``delta`` is ``after - before`` for every key in the scores map (signed;
    positive means the ``after`` artifact gained quality on that dimension).
    Comparing a file against itself yields all-zero deltas.

    Args:
        before: Filesystem path to the earlier artifact version.
        after: Filesystem path to the later artifact version.
        reference_date: Date to compute freshness age against. Defaults to
            ``None`` — when omitted, age cannot be derived (see
            :func:`~coherence.quality.score.score_text`). Threaded unchanged to
            both files for consistent assessment.
    """
    # Read file contents (supporting both str paths and Path objects)
    before_text = Path(before).read_text(encoding="utf-8")
    after_text = Path(after).read_text(encoding="utf-8")

    before_score = score_text(before_text, reference_date=reference_date)
    after_score = score_text(after_text, reference_date=reference_date)

    return {
        "before": before_score,
        "after": after_score,
        "delta": _delta(before_score, after_score),
    }


def _delta(before_score: dict, after_score: dict) -> dict:
    """Return the signed ``after - before`` delta for all score keys.

    The delta map is keyed by exactly the keys present in the ``scores`` maps
    (the open registry), each value being ``after[key] - before[key]``.
    """
    before_scores = before_score["scores"]
    after_scores = after_score["scores"]

    deltas = {key: after_scores[key] - before_scores[key] for key in after_scores.keys()}
    return deltas


__all__ = ["compare"]
