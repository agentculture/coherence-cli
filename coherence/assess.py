"""coherence.assess — one verb, every applicable domain.

``assess(path)`` is the multi-domain entry point (issue/plan-task t15,
frame claim c18): it runs **every** coherence measurement domain applicable to
a single artifact — quality, meaning, investiture — and returns ONE report,
honestly stating which domains could and could not run in this environment.
Partial availability is a normal, successful result (the CLI's future exit
code for it is 0, never an error path) — a domain that could not run is never
silently dropped; it is named in ``unavailable`` with a machine-readable code
and a human reason.

Domains run, and what "native result" means for each
-----------------------------------------------------

* **quality** (:func:`coherence.quality.score.score_text`) — rule-based, fully
  offline, always available. Its native result is the shared measurement
  envelope (:mod:`coherence.schema`): ``domain``, ``score_type``, ``scores``,
  ``frame`` (an explicit null-frame), ``diagnostics``.
* **meaning** (:func:`coherence.meaning.score.score`) — needs the embedding
  endpoint. Its native result is meaning's own pinned **two-speed** shape:
  ``meaning_score`` / ``subdimensions`` / ``diagnostics`` at the top level,
  plus the additive ``domain`` / ``score_type`` / ``frame`` keys (see
  ``docs/envelope.md``'s two-speed adoption rule) — NOT the generic
  ``scores``-map envelope quality/investiture use. When the embedding endpoint
  is unreachable, meaning cannot run, but its offline, rule-based diagnostics
  still can (:func:`coherence.meaning.score.offline_result`); those are
  preserved rather than lost (see ``unavailable`` below).
* **investiture** (:func:`coherence.investiture.score.score`) — derives
  entirely from meaning's subdimensions, so it is available if and only if
  meaning is. Its native result is the full shared envelope plus the
  issue-#8 fields (``investiture_score``, ``mode``, ``components``,
  ``evidence``). When meaning is unavailable, investiture is listed as
  unavailable too, without a second (redundant, equally doomed) attempt to
  embed.

Report shape
------------

``assess`` itself satisfies the shared measurement envelope (this repo's
"new nouns ship the full envelope from day one" rule — ``docs/envelope.md``,
frame claim c21) — ``domain == "assess"``, a descriptive ``score_type``,
``scores`` (empty: assess computes no numbers of its own; every number lives
inside ``domains``), ``frame`` (``None`` — there is no single measurement
frame for a report spanning multiple domains, each with its own), and a
top-level ``diagnostics`` list. Layered additively on top of those five keys
(``coherence.schema.validate_envelope`` only checks that the five required
keys are present and well-formed; it does not reject extra top-level keys —
the same technique :mod:`coherence.investiture.score` already relies on)::

    {"domain": "assess",
     "score_type": "multi_domain_report",
     "scores": {},
     "frame": None,
     "diagnostics": [{"code": "domain_unavailable", "message": str}, ...],
     "artifact": str(path),
     "domains": {"quality": {...envelope...},
                 "meaning": {...two-speed shape...},
                 "investiture": {...envelope + issue-8 fields...}},
     "unavailable": {"meaning": {"code": str, "reason": str,
                                 "offline_diagnostics": [{"code", "message"}, ...]},
                     "investiture": {"code": str, "reason": str}}}

``domains`` only carries a key for a domain that actually ran; ``unavailable``
only carries a key for a domain that did not. A domain is never present in
both. The top-level ``diagnostics`` list gets one ``domain_unavailable`` entry
per domain listed in ``unavailable`` — so a consumer that only reads the
top-level ``diagnostics`` list (the repo-wide ``{"code", "message"}``
convention) still sees that something was skipped, without having to know to
look inside ``unavailable``. The meaning-specific offline diagnostics (the
rule-based checks that *do* still run when the embedding endpoint is down) are
additionally surfaced verbatim at
``unavailable["meaning"]["offline_diagnostics"]`` so they are never lost —
this is the "quality + the offline diagnostics" half of a partial-availability
report.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from coherence.investiture.score import score as investiture_score
from coherence.meaning import EmbedUnavailable
from coherence.meaning.embed import embed_texts
from coherence.meaning.score import EmbedFn
from coherence.meaning.score import offline_result as meaning_offline_result
from coherence.meaning.score import score as meaning_score
from coherence.quality.score import score_text as quality_score_text
from coherence.schema import build_envelope

DOMAIN = "assess"
# assess aggregates domains of differing falsifiability classes (rule-based
# quality, model-relative meaning/investiture); it makes no falsifiability
# claim of its own, only a reporting one.
SCORE_TYPE = "multi_domain_report"

# The machine-readable reason code for "this domain needs the embedding
# endpoint and it was unreachable" — shared by meaning and (when it derives
# from an unavailable meaning) investiture.
_EMBED_UNAVAILABLE_CODE = "embed_endpoint_unreachable"
_DEFAULT_EMBED_REASON = "embedding endpoint unreachable"

# The top-level diagnostic code naming a domain that could not run this pass.
_DOMAIN_UNAVAILABLE_CODE = "domain_unavailable"


def _read_text(path: str | Path) -> str:
    """Return the UTF-8 text of the artifact at ``path``."""
    return Path(path).read_text(encoding="utf-8")


def _unavailable_entry(
    diagnostics: list[dict[str, str]],
    unavailable: dict[str, dict],
    *,
    name: str,
    code: str,
    reason: str,
    offline_diagnostics: list[dict[str, str]] | None = None,
) -> None:
    """Record ``name`` as unavailable and append its top-level diagnostic.

    Mutates ``diagnostics``/``unavailable`` in place — the shared bookkeeping
    both the meaning and investiture unavailable-branches need, so the
    "unavailable entry + top-level diagnostic, always together" invariant
    cannot drift between the two call sites.
    """
    entry: dict[str, object] = {"code": code, "reason": reason}
    if offline_diagnostics is not None:
        entry["offline_diagnostics"] = offline_diagnostics
    unavailable[name] = entry
    diagnostics.append(
        {"code": _DOMAIN_UNAVAILABLE_CODE, "message": f"{name} unavailable: {reason}"}
    )


def assess(
    path: str | Path,
    *,
    embed_fn: EmbedFn = embed_texts,
    reference_date: date | None = None,
) -> dict:
    """Run every applicable domain measurement on the artifact at ``path``.

    Always runs **quality** (offline, rule-based — never skipped). Attempts
    **meaning**, which needs the embedding endpoint; if
    :class:`~coherence.meaning.EmbedUnavailable` is raised, meaning is listed
    in ``unavailable`` (with meaning's own offline diagnostics preserved
    alongside the reason) and **investiture is not attempted at all** — it
    derives entirely from meaning's subdimensions, so a second doomed embed
    attempt would only repeat the same failure. When meaning succeeds,
    investiture is attempted separately (and, defensively, can itself be
    listed unavailable without meaning being — e.g. an ``embed_fn`` that fails
    on a later call).

    Never raises for domain unavailability: partial availability is a normal
    return, not an error (this function itself does not translate
    :class:`~coherence.meaning.EmbedUnavailable` into a CLI exit code — see
    ``coherence/cli/_commands/meaning.py``'s ``_guard`` for that pattern, which
    the future ``assess`` CLI verb will apply only to genuine input/IO errors,
    never to a domain-unavailable outcome). File I/O errors (missing path,
    directory, bad encoding, unreadable file) are NOT caught here and propagate
    to the caller, exactly as they do from :func:`coherence.quality.score.score_text`'s
    ``Path.read_text`` and :func:`coherence.meaning.score.score`'s own file read
    — that boundary conversion is the CLI's job, not this engine's.

    Args:
        path: Filesystem path to the artifact text.
        embed_fn: Batch embedder, injectable for offline tests. Threaded
            unchanged into both the meaning and investiture engines. Defaults
            to the real HTTP :func:`~coherence.meaning.embed.embed_texts`.
        reference_date: Date to compute quality's freshness age against;
            threaded unchanged into :func:`coherence.quality.score.score_text`.
            Defaults to ``None`` (this library layer never calls
            ``datetime.now()``; the CLI boundary supplies today).

    Returns:
        See the module docstring for the exact report shape.
    """
    text = _read_text(path)

    domains: dict[str, dict] = {"quality": quality_score_text(text, reference_date=reference_date)}
    unavailable: dict[str, dict] = {}
    diagnostics: list[dict[str, str]] = []

    try:
        domains["meaning"] = meaning_score(path, embed_fn=embed_fn)
    except EmbedUnavailable as exc:
        reason = str(exc) or _DEFAULT_EMBED_REASON
        offline = meaning_offline_result(path)
        _unavailable_entry(
            diagnostics,
            unavailable,
            name="meaning",
            code=_EMBED_UNAVAILABLE_CODE,
            reason=reason,
            offline_diagnostics=list(offline["diagnostics"]),
        )
        # investiture derives entirely from meaning; do not repeat the doomed
        # embed attempt, just name it unavailable for the same root cause.
        _unavailable_entry(
            diagnostics,
            unavailable,
            name="investiture",
            code=_EMBED_UNAVAILABLE_CODE,
            reason=f"derives from meaning, which is unavailable: {reason}",
        )
    else:
        try:
            domains["investiture"] = investiture_score(path, embed_fn=embed_fn)
        except EmbedUnavailable as exc:
            reason = str(exc) or _DEFAULT_EMBED_REASON
            _unavailable_entry(
                diagnostics,
                unavailable,
                name="investiture",
                code=_EMBED_UNAVAILABLE_CODE,
                reason=reason,
            )

    envelope = build_envelope(
        domain=DOMAIN,
        score_type=SCORE_TYPE,
        scores={},
        frame=None,
        diagnostics=diagnostics,
    )
    envelope["artifact"] = str(path)
    envelope["domains"] = domains
    envelope["unavailable"] = unavailable
    return envelope


__all__ = ["assess", "DOMAIN", "SCORE_TYPE"]
