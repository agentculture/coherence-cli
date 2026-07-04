# Build Plan — coherence-cli ships Meaning Gradient as a measurable coherence dimension: 'coherence meaning score <file>' returns a scalar meaning score plus per-subdimension scores and rule-based diagnostics as JSON, and 'coherence meaning compare <before> <after>' shows whether a rewrite gained or lost meaning — with the anchor sets shipped in-repo so the whole claim stays falsifiable.

slug: `coherence-cli-ships-meaning-gradient-as-a-measurab` · status: `exported` · from frame: `coherence-cli-ships-meaning-gradient-as-a-measurab`

> coherence-cli ships Meaning Gradient as a measurable coherence dimension: 'coherence meaning score <file>' returns a scalar meaning score plus per-subdimension scores and rule-based diagnostics as JSON, and 'coherence meaning compare <before> <after>' shows whether a rewrite gained or lost meaning — with the anchor sets shipped in-repo so the whole claim stays falsifiable.

## Tasks

### t1 — Meaning package scaffold + first runtime deps (pyproject.toml, coherence/meaning/__init__.py)

- covers: c3, h9
- acceptance:
  - pyproject.toml declares numpy and httpx as runtime dependencies; uv sync installs cleanly on Python 3.12
  - coherence/meaning/__init__.py exists and exports the shared error type EmbedUnavailable
  - baseline recorded: at the plan's base commit no coherence/meaning/ path and no meaning CLI noun exist (asserted in the task's PR note)

### t2 — Embedding client: env-configured OpenAI-compatible /v1/embeddings via httpx (coherence/meaning/embed.py)

- depends on: t1
- covers: c9, h7
- acceptance:
  - embed_texts(texts) POSTs to COHERENCE_EMBED_URL /embeddings with COHERENCE_EMBED_MODEL and returns one vector per input, unit-tested against a mocked httpx transport
  - connection failure or timeout raises EmbedUnavailable with an actionable hint naming the env vars; the CLI layer maps it to the environment-error exit code 2
  - defaults match eidetic's embed gear (http://localhost:8002/v1, Qwen/Qwen3-Embedding-0.6B), overridable via env

### t3 — Anchor fixtures + axis builder (coherence/meaning/axis.py, coherence/meaning/anchors/*.txt)

- depends on: t1
- covers: c8
- acceptance:
  - anchor files exist for the global meaning axis plus 5 subdimensions (consequence, agency, causality, affordance, future_constraint), high and low sets seeded from issue #4's anchor lists
  - build_axis = mean(high vectors) - mean(low vectors); project(vec, axis) returns cosine rescaled to [0,1]; unit-tested with synthetic vectors (parallel to 1.0, orthogonal to 0.5, anti-parallel to 0.0)
  - axis construction and projection are deterministic: identical anchors and vectors yield identical scores

### t4 — Rule-based diagnostics, fully offline (coherence/meaning/diagnostics.py)

- depends on: t1
- covers: c10, h3
- acceptance:
  - missing_consequence, missing_owner, missing_next_action rules run with zero network I/O
  - each rule has one positive fixture test (fires on an artifact lacking the property) and one negative fixture test (silent on an artifact having it)
  - diagnostics(text) returns a JSON-serializable list of {code, message} entries

### t5 — Score engine + JSON contract (coherence/meaning/score.py)

- depends on: t2, t3, t4
- covers: c11, h4
- acceptance:
  - score(path) returns {meaning_score, subdimensions: {consequence, agency, causality, affordance, future_constraint}, diagnostics: [...]} with every value in [0,1]
  - one embed call for the artifact plus one batch for anchors per run — no per-subdimension re-embedding of the artifact
  - adding a 6th subdimension means adding anchor files plus one registry entry; subdimensions is an open map so existing consumers need no schema change
  - with the embed endpoint down, score raises EmbedUnavailable while a diagnostics-only invocation still succeeds offline

### t6 — Compare engine: 2-point deltas (coherence/meaning/compare.py)

- depends on: t5
- covers: c4, h4
- acceptance:
  - compare(before, after) returns {before, after, delta} where delta carries a signed per-subdimension and meaning_score difference
  - compare of a file against itself yields all-zero deltas
  - output schema is unit-tested with synthetic vectors (no live endpoint needed)

### t7 — Trend engine: f-prime / f-double-prime over measurement points (coherence/meaning/trend.py)

- depends on: t2, t5
- covers: c17, h14, c18, h15
- acceptance:
  - trend(paths) with n>=2 emits per-step first differences for meaning_score, each subdimension, and embedding drift (cosine distance between consecutive artifact embeddings)
  - n>=3 additionally emits second differences per signal; n==2 marks them unavailable (null with reason) instead of erroring
  - differences are per-step and unitless; series are index-aligned: len(first)==n-1, len(second)==n-2
  - trend on exactly 2 points produces deltas identical to compare on the same files

### t8 — CLI noun wiring + explain catalog (coherence/cli/_commands/meaning.py, coherence/explain/catalog.py)

- depends on: t5, t6, t7
- covers: c1, c19
- acceptance:
  - coherence meaning noun registers score, compare, and trend verbs; all support --json; exit codes follow the 0/1/2 policy
  - trend with fewer than 2 inputs and score with a missing file exit 1 with a hint; unreachable embed gear exits 2 with a hint naming COHERENCE_EMBED_URL
  - explain catalog gains entries for meaning and each verb; bare 'coherence meaning' prints the noun overview per scaffold convention; learn and cli overview surfaces include the new noun

### t9 — Example experiment config + README (examples/experiments/issue-priority.yaml, README.md)

- depends on: t5
- covers: c13, h5, c2, h8, c5, c20, h17
- acceptance:
  - examples/experiments/issue-priority.yaml committed, matching issue #4's phase-3 shape (ratings, outcomes, features, metrics sections); no code path executes it
  - README gains a Meaning Gradient section: a coherence dimension of coherence-cli (not a separate CLI), the anchor-axis method, the three commands with JSON contract, and a consumer map stating which fields drive routing and memory decisions for steward/eidetic/taskmaster
  - README states the scope boundary: experiment runner, LLM judge, doctor/certify integration are tracked follow-ups with no code paths in the MVP

### t10 — Fixtures + offline integration tests wired into CI (tests/fixtures/meaning/, tests/test_meaning_*.py)

- depends on: t8, t9
- covers: c7, h13, h1, h10, h6, h16, h11
- acceptance:
  - high/low fixture pairs committed (including issue #4's auth-middleware pair) plus a 3-point rewrite series; real embeddings for fixtures and anchors precomputed once and committed as recorded-vector JSON so tests run offline in CI, with a refresh script to regenerate against a live endpoint
  - ordering test: every high-meaning fixture scores strictly above its paired low-meaning fixture using the recorded vectors; a failing ordering fails CI
  - schema tests: score, compare, and trend --json outputs validate against the documented schema; compare-vs-trend agreement asserted on the same 2 files
  - experiment-feature test: every meaning feature named in examples/experiments/issue-priority.yaml appears in score JSON output
  - full suite passes via the run-tests skill with zero network access

## Risks

- [unknown_nonblocking] CI has no live embed gear: integration tests rely on committed recorded-vector fixtures; changing anchors without refreshing them silently tests stale axes — refresh script plus a checksum guard mitigate (task t10)
- [unknown_nonblocking] Recorded vectors are tied to the embedding model version; upgrading the embed gear model invalidates them (regenerate via the refresh script) (task t10)
- [unknown_nonblocking] Anchor quality is unvalidated until real scores are observed; fixture ordering may require anchor tuning — a data change, not a code change (task t3)
