# The five coherence domains

coherence-cli measures coherence across five domains: quality, meaning,
signal, investiture, and frames. Each has its own package under `coherence/`,
its own JSON output shape, and its own honest limitations. This is the
one-page reference; the [README](../README.md) has the narrative version and
the module docstrings under `coherence/<domain>/` are the authoritative detail
for each engine.

Two related documents this page assumes:

- [`envelope.md`](envelope.md) — the shared five-key measurement envelope
  (`domain`, `score_type`, `scores`, `frame`, `diagnostics`) that `quality`,
  `signal`'s `collect`, `investiture`, and `assess` build their output
  through, plus the two-speed rule that lets `meaning` keep its pinned v0.5.0
  shape.
- [`signal-series.md`](signal-series.md) — the series schema `signal`'s
  engines consume (`domain`, `points`, each point's `values`/`frame`), built
  either by hand or via `coherence signal collect` from any domain's score
  JSON.

## quality

**Question it answers:** Can this context or claim be trusted, right now,
without a model call?

**Verbs:** `coherence quality score <file>`, `coherence quality compare
<before> <after>`

**Output shape:** The full shared envelope. `domain: "quality"`, `score_type:
"rule_based_heuristic"`, `scores` carries `freshness` / `provenance` /
`fidelity` plus a `<component>_confidence` entry for each, `frame` is always
an explicit null-frame (`{"available": false, "code":
"rule_based_no_embedding_frame", "reason": ...}` — quality derives no
embedding, so there is nothing to attribute), `diagnostics` names every
condition a rule could not verify. `compare` returns `{"before": ..., "after":
..., "delta": {...}}` with signed `after - before` deltas mirroring `meaning
compare`'s shape.

**Honest limitations:** These are presence-only text heuristics — regexes and
date arithmetic, nothing more. A rule can see that a URL, citation, or quote
*exists*; it cannot check that a source resolves, confirm when something was
actually published, or verify a quote's accuracy against any real record.
Every one of those gaps is a named diagnostic
(`source_liveness_unverified`, `publication_date_unverified`,
`quote_accuracy_unverified`) rather than a silently inflated score. Absence of
a dateable statement scores freshness `0.0` at low confidence — never a
fabricated positive. This is the **first practical domain** coherence-cli
ships, not a complete claim-verification system.

## meaning

**Question it answers:** What semantic structure does this artifact carry —
does it constrain future interpretation and action?

**Verbs:** `coherence meaning score <file>`, `coherence meaning compare
<before> <after>`, `coherence meaning trend <f1> <f2> <f3> ...`

**Output shape:** The pinned v0.5.0 shape (`meaning_score`, `subdimensions`,
`diagnostics`) plus **additive** top-level `domain` / `score_type` / `frame`
keys — the two-speed rule's "existing verb" side. It does *not* nest
`meaning_score`/`subdimensions` under a `scores` map; that reshape is an
explicitly versioned future migration, not part of this restructure.
`score_type` is `"model_relative_anchor_defined_projection"`. `trend` reports
per-step first/second differences (f′, f″) and embedding drift across an
ordered series of two or more artifacts.

**Honest limitations:** Scores are anchor-axis cosine projections, not a
measurement of literal meaning — parallel scores `1.0`, orthogonal `0.5`,
anti-parallel `0.0`, comparable only within the same embedding model + anchor
set (the `frame` block now names both). Three rule-based diagnostics
(`missing_consequence`, `missing_owner`, `missing_next_action`) run offline
even when the embedding endpoint is down, but `score`/`compare`/`trend`
themselves exit `2` in that case — meaning's own honest degrade path is
`offline_result`/`diagnostics_only`, used by `coherence assess`.

## signal

**Question it answers:** How do these measurements behave over time, across
versions, or against each other — and do the points that produced them share
one gauge?

**Verbs:** `coherence signal trend`, `coherence signal pattern`, `coherence
signal resonance`, `coherence signal forecast`, `coherence signal collect`

**Output shape:** Not the five-key envelope — each engine returns its own
plain, JSON-serializable dict over the shared series schema
([`signal-series.md`](signal-series.md)):

- `trend`: `{"n", "domain", "fields": {name: {"n_present", "first", "second",
  "monotonicity", "volatility", "diagnostics"}}, "diagnostics"}`.
- `pattern`: `{"n", "fields": {name: {"n_present", "motifs",
  "insufficient_points"}}, "diagnostics"}`.
- `resonance`: `{"pairs": [{"a", "b", "alignment", "relation", "n"}],
  "diagnostics"}` — `relation` is `"resonance"` (positive), `"interference"`
  (negative), or `"neutral"` (near zero), derived purely from the sign of one
  Pearson correlation, never two separate computations.
- `forecast`: `{"n", "domain", "label": "extrapolation", "fields": {name:
  {"forecast", "method", "window", "label", "n_present", ...}},
  "diagnostics"}`.
- `collect`: not an analysis — it *builds* a series-schema dict (`{"domain",
  "points"}`) from N measurement JSONs of any domain, ready to feed the four
  engines above.

**Honest limitations:** The layer is deliberately source-agnostic — it never
branches on what a field means, only on its shape, so it never crashes on
n=1/n=2/n=3+ or missing/null/non-numeric values; short or sparse fields
degrade to an explicit diagnostic and a `null` result slot instead of raising.
`forecast` is naive linear-trend-plus-recent-delta extrapolation, always
labeled `"extrapolation"` — a mechanical continuation of recent history, never
a promise about the future, and it needs a minimum of 3 present points per
field. Harmonic, wave, decay, and standalone interference-family analyses are
documented as planned and are **not built**; `resonance`'s signed metric is
the only interference coverage today. `signal` inherits the mixed-frame guard
from `coherence.frames.compat` at load time, so comparing points measured
under different gauges surfaces a visible `mixed_frames` diagnostic rather
than a silent, meaningless number.

## investiture

**Question it answers:** Did this artifact's meaning become a durable causal
imprint — did it get an owner, does it shape the future, does it create room
to act?

**Verbs:** `coherence investiture score <file>`, `coherence investiture
compare <before> <after>`

**Output shape:** The full shared envelope (`domain: "investiture"`,
`score_type: "estimated_micro_investiture"`, `scores` carrying
`investiture_score` plus the four numeric components, `frame` passed through
verbatim from the meaning engine that produced the underlying numbers,
`diagnostics`) **plus** additive top-level fields from issue #8's own
contract: `investiture_score`, `mode`, `components`, `evidence`. `compare`
returns `{"before": ..., "after": ..., "delta": {"investiture_score", ...}}`
with signed deltas over the four numeric components only.

**Honest limitations:** `mode` is always `"estimated"` — this MVP computes
`investiture_score = meaning_density × agency_coupling × future_constraint ×
affordance` from the artifact's own Meaning Gradient subdimensions alone, with
no embedding/axis logic duplicated (it calls into `coherence.meaning`
unchanged). `components.persistence_signal`, `components.integration_signal`,
and `components.behavioral_effect` are always explicit `None` — genuinely
unmeasured, never a fabricated zero — and a `missing_behavioral_outcome`
diagnostic states this on every result. `evidence` always reports
`"source": "artifact_only"`. **Investiture trace** — real evidence of
persistence, integration, or downstream behavioral effect — is a planned
extension with no code path yet (issue #8's follow-up), because there is no
history/outcome-evidence input available to measure it from today.

## frames

**Question it answers:** From which semantic coordinate frame was this
measurement taken, and is it safe to compare against another?

**Verbs:** `coherence frames inspect <measurement.json>`, `coherence frames
diff <a.json> <b.json>`

**Output shape:** Neither is the five-key envelope — the subject of `frames`
*is* the frame block, not a new score:

- `inspect`: `{"status": "complete" | "partial" | "absent", "frame",
  "missing_fields", "reason", "code", "diagnostics"}`.
- `diff`: `{"comparable": bool, "code", "message", "differing_fields",
  "soft_differences", "frame_a", "frame_b"}` — `comparable` is `True` only
  when both sides carry usable provenance and every identity field
  (`embedding_model`, `embedding_endpoint`, `anchor_set`, `projection_method`)
  matches; `axis`/`axes` and `score_type` differences are reported as
  `soft_differences` and never flip `comparable` to `False` on their own.

Every embedding-derived measurement across `meaning` and `investiture` now
carries a `frame` block built by `coherence.frames.provenance.build_frame`
(`embedding_model`, `embedding_endpoint`, `anchor_set`, `axis`/`axes`,
`projection_method`, `score_type`) — see [`envelope.md`](envelope.md). A
mixed-frame guard (`coherence.frames.compat`) is wired directly into the
`signal` series loader, so a series assembled from points measured under
different frames gets a visible warning rather than a silently wrong
comparison.

**Honest limitations:** `inspect` never errors on missing provenance — a
v0.5.0-era measurement with no `"frame"` key at all is treated as an entirely
ordinary input (`status: "absent"`), because most measurements in the wild
predate this restructure. `diff` distinguishes "neither side has provenance"
from "only one side does" from "both have provenance but disagree" — three
different failure modes, never collapsed into one generic "not comparable".
**Gauge-robustness checks** — scoring the same artifact under multiple
embedding models or anchor sets and reporting how stable the result is — are a
planned extension (issue #10) that needs more than one embed frame available
in practice first; nothing here measures robustness today, only provenance
and comparability.

## assess — the cross-domain report (not a sixth domain)

`coherence assess <file>` is not a domain of its own; it is one verb that runs
every applicable domain measurement on a single artifact and returns one
report. It satisfies the shared envelope (`domain: "assess"`, `score_type:
"multi_domain_report"`, `scores: {}` — every number lives inside `domains`,
`frame: null` — no single frame spans multiple domains), plus additive
`artifact`, `domains` (one entry per domain that ran), and `unavailable` (one
entry per domain that did not, each with a machine-readable `code` and human
`reason`). Quality always runs (fully offline); meaning and investiture are
attempted and, if the embedding endpoint is unreachable, are listed in
`unavailable` — with meaning's own offline diagnostics preserved rather than
dropped — instead of silently vanishing from the report. `signal` and
`frames` are not run automatically by `assess`; they operate over series and
measurement pairs respectively, not a single artifact in isolation.

## Language rules

Every score above is described as a **model-relative, anchor-defined
semantic measurement**, declared relative to the model/anchor set that
produced it, never treated as meaning the same thing on its own. `signal
forecast` is always labeled extrapolation, never prophecy. coherence-cli's
output and docs deliberately avoid framing a score as a physical phenomenon
or reaching for supernatural/spiritual language — see the README's
[Language and falsifiability](../README.md#language-and-falsifiability)
section.
