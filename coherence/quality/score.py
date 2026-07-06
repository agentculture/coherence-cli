"""coherence.quality.score — the offline quality score engine and envelope.

This module is the assembly point of the **quality** coherence domain: it turns
a text into the shared measurement envelope that ``coherence quality score``
will emit (see ``coherence/schema.py`` and ``docs/envelope.md``). It is fully
offline and deterministic — it wires together the rule-based component scorers
in :mod:`coherence.quality.heuristics` (freshness, provenance, fidelity), each
of which touches no network and no ``datetime.now()``.

Two honesty invariants shape the output:

* **The frame is an explicit null-frame, never fabricated.** Quality is not
  embedding-derived, so there is no model/endpoint/anchor provenance to report.
  The envelope's ``frame`` is :func:`coherence.schema.null_frame` carrying the
  machine-readable reason ``rule_based_no_embedding_frame`` — not ``None`` and
  never a made-up embedding frame.
* **Confidence is visible, and diagnostics name what a rule could not verify.**
  Each component's confidence is surfaced in ``scores`` as a
  ``<component>_confidence`` entry (a real number, not a silent omission), and
  the diagnostics list names every unverifiable / absent condition the rules
  hit (e.g. ``source_liveness_unverified``, ``no_dateable_statements``).

The engine is kept composable for the sibling quality *compare* engine (plan
task t12): :func:`assess` returns the raw component/confidence/diagnostic
breakdown, and :func:`score_text` wraps it in the shared envelope.
"""

from __future__ import annotations

from datetime import date

from coherence.quality.heuristics import (
    DIAGNOSTIC_MESSAGES,
    ComponentScore,
    score_fidelity,
    score_freshness,
    score_provenance,
)
from coherence.schema import build_envelope, null_frame

# The domain noun and the falsifiability class of its numbers, per the shared
# envelope contract. Quality is a deterministic text rule with no model
# dependency, so it is comparable across runs.
_DOMAIN = "quality"
_SCORE_TYPE = "rule_based_heuristic"

# The stable component order — freshness -> provenance -> fidelity — governs
# both the scores map and the diagnostics emission order.
_COMPONENT_ORDER = ("freshness", "provenance", "fidelity")

# The reason carried inline by the null-frame: quality derives no embedding
# frame, so its absence is stated explicitly and machine-readably.
_NULL_FRAME_CODE = "rule_based_no_embedding_frame"
_NULL_FRAME_REASON = "quality is rule-based; it derives no embedding measurement frame"


def _components(text: str, reference_date: date | None) -> dict[str, ComponentScore]:
    """Run the three component scorers over ``text`` in the stable order."""
    return {
        "freshness": score_freshness(text, reference_date),
        "provenance": score_provenance(text),
        "fidelity": score_fidelity(text),
    }


def _diagnostics(components: dict[str, ComponentScore]) -> list[dict[str, str]]:
    """Collect the components' diagnostic codes into ordered, de-duplicated entries.

    Codes are gathered in component order (a code raised by more than one
    component — e.g. ``publication_date_unverified`` — appears once, at its
    first occurrence) and mapped to their human-readable messages.
    """
    seen: set[str] = set()
    entries: list[dict[str, str]] = []
    for name in _COMPONENT_ORDER:
        for code in components[name].codes:
            if code in seen:
                continue
            seen.add(code)
            entries.append({"code": code, "message": DIAGNOSTIC_MESSAGES[code]})
    return entries


def assess(text: str, *, reference_date: date | None = None) -> dict:
    """Score ``text`` and return the raw quality breakdown (no envelope).

    Returns exactly three keys::

        {"components":  {"freshness": float, "provenance": float, "fidelity": float},
         "confidence":  {"freshness": float, "provenance": float, "fidelity": float},
         "diagnostics": [{"code": str, "message": str}, ...]}

    Every number is in ``[0, 1]``. This is the composable core the quality
    *compare* engine (task t12) subtracts on, without re-deriving the envelope.

    Args:
        text: The artifact text to assess.
        reference_date: Date to compute freshness age against. Defaults to
            ``None`` — the library never calls ``datetime.now()``; when omitted,
            a present date cannot yield an age (``age_not_derivable``). The CLI
            boundary supplies today.
    """
    components = _components(text, reference_date)
    return {
        "components": {name: components[name].score for name in _COMPONENT_ORDER},
        "confidence": {name: components[name].confidence for name in _COMPONENT_ORDER},
        "diagnostics": _diagnostics(components),
    }


def score_text(text: str, *, reference_date: date | None = None) -> dict:
    """Score ``text`` and return the shared quality measurement envelope.

    The envelope has ``domain == "quality"``, ``score_type ==
    "rule_based_heuristic"``, an explicit null-frame (never a fabricated
    embedding frame), and a ``scores`` map that carries each component's score
    *and* its confidence as a ``<component>_confidence`` entry, so confidence is
    visible rather than silent::

        scores = {"freshness": ..., "provenance": ..., "fidelity": ...,
                  "freshness_confidence": ..., "provenance_confidence": ...,
                  "fidelity_confidence": ...}

    Args:
        text: The artifact text to score.
        reference_date: Date to compute freshness age against; see
            :func:`assess`. Defaults to ``None``.
    """
    breakdown = assess(text, reference_date=reference_date)
    scores: dict[str, float] = dict(breakdown["components"])
    for name, value in breakdown["confidence"].items():
        scores[name + "_confidence"] = value
    return build_envelope(
        domain=_DOMAIN,
        score_type=_SCORE_TYPE,
        scores=scores,
        frame=null_frame(_NULL_FRAME_REASON, code=_NULL_FRAME_CODE),
        diagnostics=breakdown["diagnostics"],
    )


__all__ = ["assess", "score_text"]
