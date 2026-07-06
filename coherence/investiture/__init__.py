"""coherence.investiture — estimated meaning-as-causal-imprint measurement.

Investiture is meaning that becomes causal (issue #8): where
:mod:`coherence.meaning` measures an artifact's local semantic structure,
investiture measures the strength of that artifact as a causal imprint — was
it embedded with an actor attached, does it constrain the future, does it
create room to act. The distinction in one line::

    coherence meaning     = measures semantic structure
    coherence investiture = measures meaning-as-causal-imprint

This package's MVP measures only **estimated micro-investiture**: a
deterministic combination of the existing Meaning Gradient subdimensions
(:mod:`coherence.meaning`), computed from the artifact alone. It always reports
``mode: "estimated"`` and honestly names, via an explicit diagnostic and
explicit ``None`` component values, that persistence, integration, and
behavioral effect were NOT measured — this package has no access to git
history, recall events, or downstream behavioral labels yet (see issue #8's
scope boundary; a richer "measured" mode is a documented future extension, not
built here).

There is no mystical language anywhere in this package or its output: no
literal souls, no universal-meaning claims. Investiture is described strictly
as a falsifiable, model-relative, artifact-derived estimate.

No embedding or axis logic is duplicated here — every number comes from
:func:`coherence.meaning.score.score`, called unchanged, so this package
shares meaning's exact :class:`~coherence.meaning.EmbedUnavailable` exit-2
behavior when the embedding endpoint is unreachable.

Public surface:

* :func:`coherence.investiture.score.score` — score one artifact into the
  shared measurement envelope plus the issue-#8 fields (``investiture_score``,
  ``mode``, ``components``, ``evidence``); the CLI-facing entry point.
* :func:`coherence.investiture.compare.compare` — signed before/after
  investiture delta between two artifact versions.

CLI wiring (a ``coherence investiture`` noun) is a later task; this package is
importable and independently testable ahead of it.
"""

from __future__ import annotations

from coherence.investiture.compare import compare
from coherence.investiture.score import score

__all__ = ["score", "compare"]
