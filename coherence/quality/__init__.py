"""coherence.quality — the offline, rule-based quality coherence domain.

This is the first honest implementation of the "quality" domain long promised
by coherence-cli's tagline (freshness / provenance / fidelity of claims): a
fully OFFLINE, deterministic, rule-based first cut. It touches no network and
no ``datetime.now()`` (age is computed against a caller-supplied
``reference_date``), and it emits the shared measurement envelope
(:mod:`coherence.schema`) with ``domain == "quality"``.

Public surface:

* :func:`coherence.quality.score.score_text` — score a text into the shared
  envelope (the CLI-facing entry point).
* :func:`coherence.quality.score.assess` — the raw component/confidence/
  diagnostic breakdown, kept composable for the quality *compare* engine.
* :mod:`coherence.quality.heuristics` — the underlying rule-based detectors and
  component scorers (freshness, provenance, fidelity).
"""

from __future__ import annotations

from coherence.quality.score import assess, score_text

__all__ = ["assess", "score_text"]
