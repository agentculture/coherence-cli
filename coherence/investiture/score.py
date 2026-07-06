"""coherence.investiture.score — estimated micro-investiture from the Meaning
Gradient.

Investiture is meaning that becomes causal: not just semantic structure (what
the Meaning Gradient measures) but the strength of an artifact as a causal
imprint — did it get an owner, does it shape the future, does it create room
to act. This module's MVP measures only the ESTIMATED, artifact-only slice of
that (issue #8): it derives a score from four of the meaning engine's existing
subdimensions and honestly reports that the rest of investiture — whether the
imprint actually persisted, integrated into a system, or changed downstream
behavior — was NOT measured. There is no mystical language anywhere in this
module or its output: investiture is described as an estimated causal-imprint
measurement, never a literal soul.

No embedding/axis logic is duplicated here. Every number in this module's
output comes from :func:`coherence.meaning.score.score`, called unchanged with
the same injectable ``embed_fn`` seam meaning itself accepts — so this module
raises the identical :class:`~coherence.meaning.EmbedUnavailable` when the
embed endpoint is down (never a separately defined exception type), and it
passes the meaning engine's frame block through verbatim rather than deriving
its own.

Formula (issue #8's MVP approximation)::

    estimated_investiture = meaning_score * agency * future_constraint * affordance

Each factor is meaning's own ``[0, 1]`` projection, renamed per issue #8's
proposed component vocabulary:

* ``meaning_score``      -> ``meaning_density``    (local investiture density:
  how much meaning was embedded in the artifact at all).
* ``agency``              -> ``agency_coupling``    (is there an actor/owner
  coupled to the claim).
* ``future_constraint``   -> unchanged              (does it shape future
  behavior).
* ``affordance``          -> unchanged              (does it create room to
  act).

``consequence`` and ``causality`` (the meaning engine's other two
subdimensions) are not part of this MVP formula; a richer investiture formula
may fold them in later (see issue #8's non-goals).

Output contract — this module satisfies two overlapping shapes in ONE dict
(both required; see ``docs/envelope.md``'s two-speed rule, which classifies
``investiture`` as a NEW noun that ships the full shared envelope from day
one, unlike ``meaning``'s pinned-shape-plus-additive-keys treatment):

1. **The shared measurement envelope** (:mod:`coherence.schema`): ``domain``,
   ``score_type``, ``scores`` (the NUMERIC values only — ``investiture_score``
   plus the four numeric components), ``frame`` (the meaning engine's frame,
   passed through verbatim), ``diagnostics``.
2. **The issue-#8 JSON contract**: ``investiture_score``, ``mode``,
   ``components`` (the four numeric values *plus* ``persistence_signal`` /
   ``integration_signal`` / ``behavioral_effect`` explicitly ``None`` — never
   silently omitted, since they are genuinely unmeasured rather than zero),
   ``evidence``.

:func:`coherence.schema.validate_envelope` only checks that the five envelope
keys are *present* and individually well-formed (it loops over the five
required keys rather than asserting ``set(envelope) == {...}`` — see
``coherence/schema.py``); it does not reject extra top-level keys. So both
shapes are satisfied by placing the four issue-#8-only fields at the top
level, directly alongside the five envelope fields, rather than nesting them
under a sub-key. This keeps ``investiture_score`` reachable both via
``scores["investiture_score"]`` (the envelope-generic path any consumer that
only knows the shared contract can read) and via the top-level
``investiture_score`` key (the issue-#8 direct-access path) — the same float,
never duplicated logic.

``diagnostics`` is meaning's own diagnostics list, passed through unchanged,
with the investiture-specific ``missing_behavioral_outcome`` diagnostic
appended after them. Passing meaning's diagnostics through (rather than
dropping them) means an investiture consumer sees the same "missing owner" /
"missing next action" signals meaning already flags, without re-deriving them.
"""

from __future__ import annotations

from pathlib import Path

from coherence.meaning.embed import embed_texts
from coherence.meaning.score import EmbedFn
from coherence.meaning.score import score as meaning_score
from coherence.schema import build_envelope

# The domain noun and the falsifiability class of its numbers, per the shared
# envelope contract. "estimated_micro_investiture" names both that this is the
# MVP micro-investiture estimate (issue #8) and that it is MODE_ESTIMATED —
# artifact-only, not validated against persistence or behavioral outcomes.
DOMAIN = "investiture"
SCORE_TYPE = "estimated_micro_investiture"

# The only mode this MVP ever emits: an estimate derived purely from artifact
# structure. A future "measured" mode (backed by persistence/outcome evidence)
# is out of scope for this module (see issue #8's non-goals / trace deferral).
MODE_ESTIMATED = "estimated"

# The four meaning subdimensions this MVP formula multiplies together, named
# per issue #8's proposed component vocabulary. Order is the multiplication
# order (arbitrary, since multiplication commutes) and the stable JSON key
# order.
_MEANING_DENSITY = "meaning_density"
_AGENCY_COUPLING = "agency_coupling"
_FUTURE_CONSTRAINT = "future_constraint"
_AFFORDANCE = "affordance"
_NUMERIC_COMPONENTS: tuple[str, ...] = (
    _MEANING_DENSITY,
    _AGENCY_COUPLING,
    _FUTURE_CONSTRAINT,
    _AFFORDANCE,
)

# persistence/integration/behavioral-effect are honestly unmeasured by the
# artifact-only MVP — always an explicit None in `components`, never a silent
# omission and never a fabricated number standing in for "not measured".
_UNMEASURED_COMPONENTS: tuple[str, ...] = (
    "persistence_signal",
    "integration_signal",
    "behavioral_effect",
)

# The `evidence` block is constant for this MVP: every score comes from the
# artifact alone, with no history or outcome-label input available yet.
_EVIDENCE_ARTIFACT_ONLY: dict[str, object] = {
    "source": "artifact_only",
    "has_history": False,
    "has_outcome_labels": False,
}

# The one diagnostic this module always adds, honestly naming what was not
# measured (issue #8's acceptance criterion: "explicitly reporting that
# persistence/behavioral effect were NOT measured").
_MISSING_BEHAVIORAL_OUTCOME_DIAGNOSTIC: dict[str, str] = {
    "code": "missing_behavioral_outcome",
    "message": (
        "Investiture is estimated from artifact structure only; no downstream "
        "behavior was measured."
    ),
}


def _numeric_components(meaning_result: dict) -> dict[str, float]:
    """Map the meaning result's relevant fields onto issue #8's component names."""
    subdimensions = meaning_result["subdimensions"]
    return {
        _MEANING_DENSITY: meaning_result["meaning_score"],
        _AGENCY_COUPLING: subdimensions["agency"],
        _FUTURE_CONSTRAINT: subdimensions["future_constraint"],
        _AFFORDANCE: subdimensions["affordance"],
    }


def _investiture_score(numeric_components: dict[str, float]) -> float:
    """Multiply the four numeric components together (the issue #8 formula)."""
    value = 1.0
    for name in _NUMERIC_COMPONENTS:
        value *= numeric_components[name]
    return value


def score(path: str | Path, *, embed_fn: EmbedFn = embed_texts) -> dict:
    """Score the artifact at ``path`` and return the investiture measurement.

    Reuses :func:`coherence.meaning.score.score` for every embedding/axis
    computation; this function only combines meaning's own numbers into an
    estimated investiture score and wraps them in the shared envelope plus the
    issue-#8 fields (see module docstring for the exact shape).

    Args:
        path: Filesystem path to the artifact text.
        embed_fn: Batch embedder, injectable for offline tests. Threaded
            unchanged into :func:`coherence.meaning.score.score`. Defaults to
            the real HTTP :func:`~coherence.meaning.embed.embed_texts`, which
            raises :class:`~coherence.meaning.EmbedUnavailable` if the
            embedding endpoint is down — this function does not catch that
            exception, so it propagates unchanged (the same exit-2 path
            ``coherence meaning score`` already uses).
    """
    meaning_result = meaning_score(path, embed_fn=embed_fn)

    numeric_components = _numeric_components(meaning_result)
    investiture_score_value = _investiture_score(numeric_components)

    components: dict[str, float | None] = dict(numeric_components)
    for name in _UNMEASURED_COMPONENTS:
        components[name] = None

    scores: dict[str, float] = dict(numeric_components)
    scores["investiture_score"] = investiture_score_value

    diagnostics = list(meaning_result["diagnostics"])
    diagnostics.append(dict(_MISSING_BEHAVIORAL_OUTCOME_DIAGNOSTIC))

    envelope = build_envelope(
        domain=DOMAIN,
        score_type=SCORE_TYPE,
        scores=scores,
        frame=meaning_result["frame"],
        diagnostics=diagnostics,
    )
    # The issue-#8 fields, additive alongside the five envelope keys (see
    # module docstring — validate_envelope tolerates extra top-level keys).
    envelope["investiture_score"] = investiture_score_value
    envelope["mode"] = MODE_ESTIMATED
    envelope["components"] = components
    envelope["evidence"] = dict(_EVIDENCE_ARTIFACT_ONLY)
    return envelope


__all__ = ["score", "DOMAIN", "SCORE_TYPE", "MODE_ESTIMATED", "EmbedFn"]
