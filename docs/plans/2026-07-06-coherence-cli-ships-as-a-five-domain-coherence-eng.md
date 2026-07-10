# Build Plan — coherence-cli ships as a five-domain coherence engine — quality, meaning, signal, investiture, and frames — so agents can measure, analyze, assess, and predict the coherence of content before acting on it

slug: `coherence-cli-ships-as-a-five-domain-coherence-eng` · status: `exported` · from frame: `coherence-cli-ships-as-a-five-domain-coherence-eng`

> coherence-cli ships as a five-domain coherence engine — quality, meaning, signal, investiture, and frames — so agents can measure, analyze, assess, and predict the coherence of content before acting on it

## Tasks

### t1 — t1 Shared measurement envelope: coherence/schema.py defining the envelope (domain, score_type, scores, frame, diagnostics) with build/validate helpers + docs/envelope.md documenting the two-speed adoption rule

- covers: c14
- acceptance:
  - coherence.schema exposes a build_envelope/validate_envelope pair; a valid envelope round-trips and a missing 'domain' or non-dict 'scores' is rejected with a named error
  - docs/envelope.md documents all five envelope fields and states the two-speed rule: new nouns emit full envelope, existing meaning verbs gain only additive top-level keys

### t2 — t2 Frame provenance core: coherence/frames/provenance.py builds the frame block (embedding_model, embedding_endpoint, anchor_set, axis/axes, projection_method, score_type) from the RESOLVED runtime embed config; explicit absent-provenance representation

- depends on: t1
- covers: c13
- acceptance:
  - frame block reflects COHERENCE_EMBED_URL/COHERENCE_EMBED_MODEL as resolved at call time (monkeypatched env changes the emitted block; defaults appear only when env is unset)
  - absent provenance is representable as an explicit null-frame with a machine-readable reason, never a missing key

### t3 — t3 Signal series schema: coherence/signal/schema.py — documented source-agnostic series input schema (per-point id/index/timestamp/values + optional per-point frame), robust loader

- depends on: t1
- covers: c11, h7
- acceptance:
  - loader accepts a hand-written series with arbitrary numeric value names AND a series converted from meaning trend output (source-agnosticism proven by test)
  - n=1, n=2, n=3+ series load; missing/null/non-numeric values are skipped-with-diagnostic, never a crash
  - the series schema is documented (docs or module docstring referenced from docs) including the optional per-point frame field

### t4 — t4 signal trend engine: coherence/signal/trend.py — first/second differences, monotonicity, volatility diagnostics over any numeric series field

- depends on: t3
- covers: c11
- acceptance:
  - 2 points yield f-prime, 3+ points yield f-double-prime, per field; 1 point yields an explicit too-short diagnostic and no differences
  - monotonicity (increasing/decreasing/mixed) and a simple volatility measure are reported per field

### t6 — t6 signal pattern engine: coherence/signal/pattern.py — motif detection: increasing, decreasing, plateau, spike, reversal, stair_step

- depends on: t3
- covers: c11
- acceptance:
  - each of the six motifs is detected on a synthetic series constructed to exhibit it, and not detected on a counterexample series
  - short series (n<3) return an explicit insufficient-points diagnostic instead of motifs

### t7 — t7 signal resonance engine with SIGNED alignment: coherence/signal/resonance.py — pairwise correlation between numeric fields; positive pairs reported as resonance, negative pairs as interference, one signed metric

- depends on: t3
- covers: c11, c22, h17
- acceptance:
  - two fields rising together yield a positive-alignment pair; one rising while the other falls yields a negative (interference) pair — from the same code path (test asserts sign symmetry)
  - constant or too-short fields are excluded with a diagnostic, not NaN correlations

### t8 — t8 signal forecast engine: coherence/signal/forecast.py — naive next-point extrapolation (linear trend + recent-delta blend), minimum-points guard, output labeled as extrapolation naming window/method

- depends on: t4
- covers: c17, h13
- acceptance:
  - below the minimum-points threshold the engine raises the user-error path that the CLI maps to exit 1 with a hint
  - a constant series forecasts the constant; a strictly linear series extends the line (both asserted numerically)
  - output includes method name, window used, and an explicit extrapolation label

### t9 — t9 signal collect: coherence/signal/collect.py — build a valid series file from N envelope-bearing measurement JSONs of any domain, preserving order and carrying per-point frame provenance

- depends on: t3
- covers: c24, h19
- acceptance:
  - collect accepts meaning, quality, and investiture score JSONs in one call (envelope-driven, no per-domain branches) and emits a series that the signal loader validates
  - input ordering is preserved and each point carries the source measurement's frame block (or explicit null-frame)

### t10 — t10 meaning outputs gain additive envelope keys: score/compare/trend JSON gains top-level domain, score_type, and frame (from coherence.frames.provenance); existing keys untouched

- depends on: t2
- covers: c13, c7, h9
- acceptance:
  - meaning score --json contains domain=meaning, a score_type string, and a frame block reporting the runtime-resolved endpoint/model/anchor-set/projection
  - every pre-existing key of score/compare/trend output is byte-identical to v0.5.0 on the recorded fixtures (additive-only proven by golden subset test)
  - with the embed endpoint unreachable, the offline-diagnostics path still emits an explicit null-frame with reason rather than a fabricated frame

### t11 — t11 quality domain engine (greenfield): coherence/quality/heuristics.py + score.py — offline rule-based freshness (dateable statements, derivable age), provenance (source attribution), fidelity (quote-vs-paraphrase signals); emits full envelope with domain=quality

- depends on: t1
- covers: c16, h12
- acceptance:
  - quality score runs with zero network access (test blocks sockets) and emits the shared envelope with domain=quality
  - diagnostics name what heuristics could NOT verify (source liveness, actual publication date) — asserted present on an artifact with citations
  - an artifact with no dateable statements gets lowered confidence with a diagnostic, never a fabricated freshness score

### t12 — t12 quality compare: coherence/quality/compare.py — before/after quality with signed per-component deltas mirroring meaning compare's shape

- depends on: t11
- covers: c25, h20
- acceptance:
  - compare emits before/after envelopes plus a delta map whose keys mirror the quality components, all signed
  - runs fully offline like quality score (same socket-blocked test harness)

### t13 — t13 investiture noun engine: coherence/investiture/score.py + compare.py — estimated micro-investiture from meaning subdimensions via coherence.meaning (no duplicate embed path); mode, components, evidence, diagnostics; compare with signed deltas

- depends on: t10
- covers: c12, h8
- acceptance:
  - score output carries investiture_score, mode=estimated, components (with persistence_signal/integration_signal/behavioral_effect explicitly null), evidence flags, and the missing-behavioral-outcome diagnostic
  - with the embed endpoint unreachable, score surfaces the same exit-2 hint as meaning (proving reuse of coherence.meaning, asserted via shared error type)
  - compare emits before/after scores and signed component deltas; investiture output uses the full shared envelope and passes through the meaning frame block

### t14 — t14 frames noun: coherence/frames/inspect.py + diff.py + compat.py — inspect provenance completeness of any measurement JSON; diff two measurements for frame-comparability; mixed-frame guard callable wired into the signal series loader

- depends on: t2, t3
- covers: c23, h18
- acceptance:
  - inspect on a v0.5.0-era JSON (no frame block) reports missing provenance explicitly with exit 0 and a diagnostic, not an error
  - diff on two measurements with different embedding_model reports not-comparable with the differing fields named
  - a series with mixed per-point frames produces a visible mixed-frame warning diagnostic when loaded (exercised via the signal loader test), never a silent number

### t15 — t15 assess engine: coherence/assess.py — run every applicable domain (quality heuristics, meaning scores, investiture estimate) into one multi-domain report using the shared envelope, with per-domain availability honestly reported

- depends on: t11, t13
- covers: c18, h14
- acceptance:
  - with the embed endpoint mocked down, assess returns quality + offline diagnostics and lists meaning/investiture as unavailable with reasons (partial availability, exit 0)
  - with the endpoint up (recorded vectors), the report contains one envelope per available domain keyed by domain name

### t17 — t17 README + docs restructure: five-domain positioning replaces the tagline, domains section, claim quality named first practical domain, envelope + two-speed rule documented, model-relative anchor-defined language, planned-extensions list (harmonic/wave/decay, robustness, trace, experiment runner)

- depends on: t15
- covers: c3, h2, c5, h4, c14, h10
- acceptance:
  - README leads with the five-domain coherence-engine positioning and names claim quality as the first practical domain, not the whole product
  - docs describe scores as model-relative, anchor-defined semantic measurements and anchors as axes/observables; no mystical or universal-meaning language (grep-able banned-terms check)
  - the consumer map (steward/eidetic/taskmaster/colleague) remains present and accurate; deferred work is listed as planned extensions with issue links

### t5 — t5 meaning trend delegation: coherence/meaning/trend.py difference math replaced by calls into coherence.signal.trend; meaning trend becomes a dimension-specific wrapper; mixed-frame warning arrives via the shared path

- depends on: t4, t10
- covers: c15, h11
- acceptance:
  - meaning trend --json output on the recorded-vector fixtures is byte-identical before and after the refactor (guarded by a golden-output test)
  - no difference math remains in coherence/meaning/trend.py (only orchestration, output assembly, and meaning-specific labeling)

### t16 — t16 CLI wiring for all new nouns: cli/_commands/quality.py, signal.py, investiture.py, frames.py, assess.py + explain catalog entries (incl. semantic frame, frame provenance, model-relative score, anchor-relative score, gauge-robust score, field sample, trajectory, signal) + cli overview/learn updates

- depends on: t5, t6, t7, t8, t9, t12, t13, t14, t15
- covers: c1, h16
- acceptance:
  - every new verb (quality score/compare, signal trend/pattern/resonance/forecast/collect, investiture score/compare, frames inspect/diff, assess) supports --json and exit codes 0/1/2 per scaffold conventions
  - coherence explain resolves every new noun/verb path and the eight frame-vocabulary terms; cli overview and learn list all five domains
  - measure/analyze/assess/predict each maps to at least one working command (score verbs / signal verbs / assess / forecast) — asserted by an explain-catalog or help-surface test

### t18 — t18 offline fixtures + integration verification: recorded-vector reuse for investiture/assess, quality/signal fixtures, additive-only pre/post output diff proof, colleague fixture additive-tolerance verification (h15 guard), full suite green

- depends on: t16, t17
- covers: c2, h1, c4, h3, c6, h5, h6
- acceptance:
  - all new-noun tests run offline from committed fixtures (CI has no embed endpoint); pre-existing meaning assertions unmodified except additive-key tolerance
  - a pre/post diff test proves every pre-existing command's output gained only added keys (no key removed, renamed, or retyped)
  - colleague's gate fixture (colleague#291/#294) is verified additive-tolerant or colleague's sign-off is recorded on the PR before merge
  - a fresh-checkout test asserts a package home per domain and signal+investiture+quality+frames+assess registered as CLI nouns

## Risks

- [unknown_nonblocking] colleague's gate fixture may not be additive-tolerant in practice — h15 guard requires verification against colleague#291/#294 or colleague sign-off before merge (task t18)
- [unknown_nonblocking] quality heuristics (freshness/provenance/fidelity rules) are unvalidated until run against real artifacts — scores may need retuning; the honest-diagnostics contract is the mitigation (task t11)
- [unknown_nonblocking] recorded-vector fixtures are tied to the embed model version (inherited meaning-gradient risk r2); investiture/assess reuse them, so an anchor or model change requires the refresh script across MORE test surfaces (task t18)
