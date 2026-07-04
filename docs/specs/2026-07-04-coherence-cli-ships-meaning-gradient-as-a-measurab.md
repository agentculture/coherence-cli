# coherence-cli ships Meaning Gradient as a measurable coherence dimension: 'coherence meaning score <file>' returns a scalar meaning score plus per-subdimension scores and rule-based diagnostics as JSON, and 'coherence meaning compare <before> <after>' shows whether a rewrite gained or lost meaning — with the anchor sets shipped in-repo so the whole claim stays falsifiable.

> coherence-cli ships Meaning Gradient as a measurable coherence dimension: 'coherence meaning score <file>' returns a scalar meaning score plus per-subdimension scores and rule-based diagnostics as JSON, and 'coherence meaning compare <before> <after>' shows whether a rewrite gained or lost meaning — with the anchor sets shipped in-repo so the whole claim stays falsifiable.

## Audience

- Agents and operators in the AgentCulture mesh that route, remember, compress, or gate artifacts (steward, eidetic, taskmaster, colleague) — plus humans triaging issues and reviewing rewrites.

## Before → After

- Before: coherence-cli is a bare scaffold (whoami/learn/explain/doctor only, zero runtime deps); meaning of artifacts is judged by vibes — no measurable signal, no way to test whether a rewrite added meaning, no instrumentation to falsify the Meaning Gradient thesis.
- After: 'coherence meaning score <file>' emits JSON with meaning_score, at least 4 subdimension scores, and rule-based diagnostics (missing_consequence / missing_owner / missing_next_action); 'coherence meaning compare before after' emits per-subdimension deltas; anchor sets live in-repo as editable fixtures.

## Why it matters

- Routing, memory, compression, and certification policies need a signal that predicts what humans and agents remember, prioritize, and execute — and the claim must stay empirical: instrumentation first, so the phase-3 experiment can prove or disprove predictive value.

## Requirements

- Scoring uses anchor-axis projection: embed the artifact, build meaning_axis = mean(high-anchor embeddings) - mean(low-anchor embeddings), score = cosine(artifact, axis) normalized to [0,1]; each subdimension gets its own high/low anchor pair set.
  - honesty: Scoring is deterministic for a fixed anchor set + embedding endpoint, and on the shipped fixtures every high-meaning artifact scores strictly above its paired low-meaning artifact.
- Embeddings come from an OpenAI-compatible /v1/embeddings endpoint configured via env (COHERENCE_EMBED_URL / COHERENCE_EMBED_MODEL, defaulting to the same local embed gear eidetic uses); when unreachable, score exits with the CLI's environment-error code and a clear hint, while rule-based diagnostics still run offline.
  - honesty: With the embed endpoint down, 'coherence meaning score' exits with the environment-error code and an actionable hint, and a diagnostics-only invocation still succeeds offline.
- Rule-based diagnostics detect missing_consequence, missing_owner, and missing_next_action without any embedding call, and land in the JSON output as a diagnostics list.
  - honesty: Each diagnostic rule fires on a fixture artifact that lacks the property and stays silent on a fixture that has it — one positive and one negative test per rule.
- MVP ships 5 subdimensions — consequence, agency, causality, affordance, future_constraint — chosen from the issue's 'most important for Culture.dev' list; the JSON schema leaves room to add more without breaking consumers.
  - honesty: All 5 subdimensions appear in the score JSON with values in [0,1], and compare emits a signed delta per subdimension; adding a 6th subdimension later requires no schema change for existing consumers.
- An example experiment config (issue-priority YAML, per issue #4 phase 3 shape) ships under examples/ as a committed artifact so the falsifiability path is visible — but the runner itself is out of scope.
  - honesty: The example experiment YAML parses against the documented config shape and is referenced from the README; no code path executes it.

## Honesty conditions

- Both commands exist and emit valid JSON matching the documented schema; the README states Meaning Gradient is a coherence dimension of coherence-cli, not a separate tool; issue #4's minimum-tier acceptance boxes are all checkable.
- At least one named mesh consumer can act on the score JSON without human translation — schema fields map directly to a routing or memory decision.
- Before this lands the repo has no 'meaning' noun and no scoring code — verifiable against the scaffold at the spec's base commit.
- Running both commands on the shipped fixtures reproduces the documented JSON shape exactly, validated in tests.
- Every meaning feature the phase-3 experiment YAML names is emitted by 'coherence meaning score' — the MVP output is a sufficient input for the deferred experiment.
- No MVP code path executes an experiment, calls an LLM judge, or touches doctor/certify; each deferred phase is a tracked follow-up, not silent scope.
- CI runs the fixture-ordering and diagnostic tests; a failing high/low ordering fails the build.

## Success signals

- On repo fixtures, score orders each high-meaning rewrite above its low-meaning original (e.g. the issue's auth-middleware pair); the JSON contract and each diagnostic rule are exercised by tests; README documents Meaning Gradient as a coherence dimension.

## Scope / boundaries

- This spec covers issue #4 phases 1-2 only (score + compare). No separate meaning-cli, no LLM judge, no experiment runner execution, no doctor/certify integration, no pluggable embedding providers — those are tracked follow-ups, not silent scope.

## Non-goals

- The MVP does not claim meaning is 'solved' or predictive; it ships the instrumentation needed to prove or disprove the thesis empirically.

## Assumptions

- Anchor-axis projection yields a signal that is not just length or sentiment in disguise — this is exactly what the phase-3 experiment must test; the MVP makes no predictive-validity claim.

## Decisions

- Runtime deps for the meaning engine: numpy (vector math) and httpx (embedding HTTP) are allowed as the package's first runtime dependencies — chosen over stdlib-only because phase 3 (experiments, cross-validation) lands in this same package next. Anchors stay plain-text fixtures; the scaffold's agent-first CLI conventions (exit codes 0/1/2, --json, explain catalog entry) apply to the new noun.

## Open / follow-up

- Phase 3: 'coherence meaning experiment run' + a 100-300 issue human-rated dataset (needs human raters and outcome labels).
- Phases 4-5: 'coherence doctor --dimension meaning' and 'coherence certify --dimension meaning' — integrate once scoring is trusted.
- LLM-judge fallback and pluggable embedding providers (issue #4 stretch tier).
- Culture.dev routing policy output (route_to / memory_candidate recommendations) — depends on validated scores.
