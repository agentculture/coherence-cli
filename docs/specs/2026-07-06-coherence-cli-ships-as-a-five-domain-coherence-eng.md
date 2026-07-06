# coherence-cli ships as a five-domain coherence engine — quality, meaning, signal, investiture, and frames — so agents can measure, analyze, assess, and predict the coherence of content before acting on it

> coherence-cli ships as a five-domain coherence engine — quality, meaning, signal, investiture, and frames — so agents can measure, analyze, assess, and predict the coherence of content before acting on it

## Audience

- Agentic-mesh consumers of score JSON — colleague's post-loop coherence gate (first wired consumer), steward, eidetic, taskmaster — plus the humans operating coherence-cli directly

## Before → After

- Before: meaning is the only implemented domain (score/compare/trend, v0.5.0); the README tagline promises claim-quality (freshness/provenance/fidelity) that has NO code behind it; no signal, investiture, or frames code exists; score JSON carries no provenance of the embedding frame that produced it
- After: coherence-cli is positioned and structured as a five-domain coherence engine: quality, meaning, signal, investiture, frames each have a package home and docs; signal and investiture ship as new CLI nouns; every measurement JSON gains an additive frame/provenance block and a shared envelope direction (domain, score_type, scores, frame, diagnostics); existing meaning commands keep their exact JSON shape modulo additive keys

## Why it matters

- The one-domain tagline is now false in both directions (promises unbuilt quality checks, hides shipped meaning measurement); frame provenance makes scores falsifiable (model-relative, anchor-defined, declared gauge) instead of pretending universal meaning; a reusable signal layer means every current and future dimension gets trend/pattern/resonance analysis without reimplementation

## Requirements

- signal noun (#9 MVP): documented source-agnostic series input schema; 'coherence signal trend' (first/second differences + monotonicity/volatility diagnostics), 'coherence signal pattern' (motifs: increasing, decreasing, plateau, spike, reversal, stair-step), 'coherence signal resonance' (pairwise alignment/correlation between numeric fields); harmonic/wave/decay/interference documented as planned; handles n=1, n=2, n=3+ and missing/null/non-numeric values without crashing
  - honesty: the same signal verb accepts a series converted from meaning trend output AND a hand-written series with arbitrary numeric value names (proving source-agnosticism), and tests cover n=1, n=2, n=3+, plus missing/null/non-numeric values without crashing
- investiture noun (#8 MVP): 'coherence investiture score' returns investiture_score, mode, components, evidence, diagnostics — computed from existing Meaning Gradient subdimensions in mode:estimated, explicitly reporting that persistence/behavioral effect were NOT measured; 'coherence investiture compare' returns before/after scores and signed deltas; trace deferred; calls into coherence.meaning rather than duplicating embedding/axis logic
  - honesty: artifact-only investiture output always carries mode:estimated plus a diagnostic stating persistence/behavioral effect were not measured; with the embed endpoint down it exits 2 with the same actionable hint as meaning (it reuses coherence.meaning, not a duplicate embed path)
- frames domain (#10 MVP): meaning score/compare/trend JSON gains an additive frame block (embedding_model, embedding_endpoint, anchor_set, axis/axes, projection_method, score_type); investiture and signal outputs carry or pass through frame provenance where the source has it; missing provenance is handled explicitly, not silently; explain catalog gains: semantic frame, frame provenance, model-relative score, anchor-relative score, gauge-robust score, field sample, trajectory, signal
  - honesty: the frame block reports the endpoint/model actually used at runtime (resolved env config, not hardcoded defaults); when a signal input lacks provenance the output says so explicitly (null frame + diagnostic) rather than omitting the key
- restructure (#11): package gains clear domain boundaries (quality/, meaning/, signal/, investiture/, frames/ as applicable); README leads with the five-domain coherence-engine positioning and a domains section; measurement JSON documents the shared-envelope direction (domain, score_type, scores, frame, diagnostics) with backward compatibility for existing consumers
  - honesty: README + explain catalog present all five domains with claim quality named as the first practical domain; the shared envelope is documented with its two-speed adoption rule; all pre-existing tests still pass
- meaning trend delegates its difference math to the signal layer (coherence.signal.trend) so 'meaning trend' becomes a dimension-specific wrapper and behavior stays identical
  - honesty: meaning trend --json output on the recorded-vector fixtures is byte-identical before and after the delegation refactor
- quality domain MVP (greenfield, replaces #11's 'preserve existing code' premise): 'coherence quality score <file>' — fully offline, rule-based first cut scoring freshness (dateable statements present/absent, age when derivable), provenance (source attribution present/absent), fidelity (quoted-vs-paraphrased signals), task validity hooks — emitting the shared envelope with domain:quality and honest diagnostics for what a heuristic cannot measure
  - honesty: quality score runs with zero network access; its diagnostics name what the heuristics could NOT verify (e.g. source liveness, actual publication date) instead of inflating scores; absence of dateable statements lowers confidence, never fabricates freshness
- predict surface: 'coherence signal forecast <series.json>' — naive next-point extrapolation (linear trend + recent-delta blend) with explicit confidence caveats and a minimum-points guard; documented as extrapolation of a declared frame's signal, not prophecy
  - honesty: forecast exits 1 with a hint below the minimum-points threshold; output is labeled as extrapolation and names the window/method used; a constant series forecasts the constant and a linear series extends the line
- assess surface: 'coherence assess <file>' — one verb that runs every applicable domain measurement (quality heuristics, meaning scores, investiture estimate) and emits a single multi-domain report using the shared envelope, with per-domain availability honestly reported (e.g. embed endpoint down means meaning absent, quality still present)
  - honesty: with the embed endpoint down, assess still returns the offline domains (quality, rule-based diagnostics) and explicitly lists meaning/investiture as unavailable — partial availability is reported, never silently dropped
- signal resonance reports SIGNED alignment: positively aligned pairs (resonance) and negatively aligned pairs (interference) from the same computation — answering both 'do these streams reinforce?' and 'do these streams conflict?' in the MVP instead of deferring interference
  - honesty: resonance output on a series where two fields rise together yields a positive pair, and where one rises while another falls yields a negative (interference) pair; both come from one signed metric, not two code paths
- frames becomes a real noun, not just metadata: 'coherence frames inspect <score.json>' reports the frame that produced a measurement and whether provenance is complete; 'coherence frames diff <a.json> <b.json>' answers whether two measurements are frame-comparable (same gauge) — and meaning trend / signal verbs WARN when fed measurements from mixed frames, guarding the silent cross-gauge comparison error
  - honesty: frames inspect on a v0.5.0-era JSON (no frame block) reports missing provenance explicitly instead of erroring; frames diff on two measurements from different embed models reports not-comparable; feeding mixed-frame inputs to trend produces a visible warning, never a silent number
- 'coherence signal collect <score.json>...' builds a series file (the documented signal input schema) from N envelope-bearing measurement JSONs of any domain — the glue that turns per-artifact measurements into analyzable/forecastable signals without hand-authoring series files
  - honesty: collect accepts meaning, quality, and investiture score JSONs alike (envelope-driven, no per-domain code), preserves input ordering, carries frame provenance through to the series, and its output validates against the same series schema signal verbs consume
- 'coherence quality compare <before> <after>' ships alongside quality score — uniform verb grammar (score/compare) across measuring domains, so rewrites can be evaluated for quality deltas exactly like meaning deltas
  - honesty: quality compare emits signed per-component deltas mirroring meaning compare's shape, and runs fully offline like quality score

## Honesty conditions

- the announcement is honest only if all five domains are real at ship time: each has a package home, docs, and at least one working measurement path (meaning already shipped; quality/signal/investiture ship verbs; frames ships as provenance on every embedding-derived output) — 'measure, analyze, assess, predict' each maps to a concrete command
- colleague's coherence gate validates against the restructured meaning JSON without editing its pinned fixture (additive keys only), and the steward/eidetic/taskmaster consumer-map rows in README remain accurate after repositioning
- verifiable by inspection at branch point: no quality/signal/investiture/frames packages exist under coherence/, and the README tagline promises freshness/provenance/fidelity behavior git grep cannot find an implementation for
- on the merged result, a fresh checkout shows a package home per domain, signal+investiture registered as CLI nouns, and a diff of 'meaning score --json' output vs v0.5.0 that is purely additive (no key removed, renamed, or retyped)
- after the change, every emitted embedding-derived score JSON names the frame that produced it (model, endpoint, anchor set, projection method), so a consumer can distinguish measurements from different gauges
- CI passes with the pre-existing meaning test assertions unmodified except where they gain additive-key tolerance; every new-noun test runs offline from committed fixtures; 'coherence explain' resolves every new noun/verb path
- a pre/post diff of every pre-existing command's output shows only added keys — no verb, flag, key, or exit-code semantic is removed or renamed in this restructure
- confirmed against colleague's actual gate fixture (colleague#291/#294): its assertion style is subset/additive-tolerant, or colleague signs off on the additive frame block before this merges

## Success signals

- All existing tests keep passing and colleague's pinned 'meaning score --json' fixture still validates (only additive keys); each new noun ships with --json, exit codes 0/1/2, explain-catalog entries, and offline tests; README leads with the five-domain positioning and names claim quality as the first practical domain, not the whole product

## Scope / boundaries

- No breaking CLI changes: existing meaning commands and their JSON stay valid; renames arrive as aliases or a documented versioned migration, never silently

## Non-goals

- No FFT / physical wave modeling, no LLM-judge dependency, no cross-model embedding transformations, no gauge-invariant scoring, no proof of long-term behavioral causality — all documented as planned extensions, not built
- No mystical language in CLI output or docs: no literal physics, no literal souls, no universal-meaning claims — scores are described as model-relative, anchor-defined semantic measurements
- No full rewrite: the shipped meaning engine is preserved and reframed as one domain of five, not reimplemented

## Assumptions

- colleague's pinned fixture tolerates additive keys in 'meaning score --json' (its #11 comment commits to passing a native frame block through verbatim), so the frame block can land without a compatibility mode

## Decisions

- package layout uses coherence/quality/ (not claims/) — #11's own criterion prefers quality/ when scope exceeds individual claims, and the greenfield domain is defined broader than claim checks
- envelope adoption is two-speed: NEW nouns (quality, signal, investiture, assess) emit the full shared envelope (domain, score_type, scores, frame, diagnostics) from day one; EXISTING meaning verbs keep their pinned shape and gain only additive top-level keys (domain, score_type, frame) — nesting meaning_score/subdimensions under scores is deferred to an explicitly versioned future migration

## Open / follow-up

- harmonic, wave, decay, interference signal analyses — documented as planned families, built only after real series data exists
- gauge-robustness checks (meaning robustness / signal robustness across models and anchor sets) — documented as planned extension per #10, needs multiple embed frames available
- investiture trace verb — needs history/outcome evidence sources (git survival, recall events, downstream references) that do not exist as inputs yet
- meaning experiment runner, doctor --dimension, certify --dimension, LLM-judge fallback, routing-policy output — already-tracked #4/#6 roadmap, untouched by this restructure
- freshness half-life / staleness-date prediction (quality x time decay model) — a real 'predict coherence' direction but needs longitudinal data before a model is honest
