# coherence-cli

Measures and maintains coherence in agentic systems — turning context, claims,
meaning, provenance, and behavioral traces into inspectable signals so agents
can decide what to trust, refresh, repair, route, or remember.

## Why agents need coherence

Agents consume artifacts — files, claims, other agents' outputs, their own
prior memory — with no reliable way to ask "should I trust this, and why?"
before acting on it. coherence-cli turns that judgment into a small set of
inspectable, reproducible measurements: offline rule-based heuristics where no
model is needed, model-relative embedding projections where a semantic axis is
the right instrument, and trajectory analysis where the question is how a
measurement moves over time. Every measurement carries honest diagnostics
about what it could and could **not** verify, so a downstream consumer — a
mesh agent, a CLI script, a human — can decide whether to trust an artifact,
refresh it, repair it, route it, or store it in memory, instead of treating a
lone number as ground truth.

## The five coherence domains

coherence-cli ships five coherence domains, each with its own package under
`coherence/`, its own docs, and at least one working measurement path. See
[`docs/domains.md`](docs/domains.md) for the one-page reference (question →
verbs → output shape → honest limitations, per domain).

| Domain | Question it answers | What it ships |
|--------|---------------------|----------------|
| **quality** | Can this context or claim be trusted, right now, without a model call? | Offline, rule-based freshness/provenance/fidelity heuristics with honest can't-verify diagnostics — the **first practical domain** (not the whole product). |
| **meaning** | What semantic structure does this artifact carry — does it constrain future interpretation and action? | The shipped Meaning Gradient (`coherence meaning score/compare/trend`). |
| **signal** | How do these measurements behave over time, across versions, or against each other? | Trend (f′/f″), pattern (motif detection), resonance + interference (signed alignment), forecast (labeled extrapolation), and collect (build a series from any domain's score JSON). |
| **investiture** | Did this artifact's meaning become a durable causal imprint? | An **estimated** micro-investiture score derived from Meaning Gradient subdimensions — artifact-only, honestly diagnosed as not measuring persistence or behavioral effect. |
| **frames** | From which semantic coordinate frame was this measurement taken — and is it safe to compare against another? | Provenance attached to every embedding-derived score, plus `inspect`/`diff` verbs and a mixed-frame guard. |

### quality — the first practical domain

`coherence quality` is fully offline and rule-based: no embeddings, no
network, no `datetime.now()` (age is computed against a supplied reference
date). It scores three components — **freshness** (is there a dateable
statement, and how old is it?), **provenance** (is there source attribution?),
**fidelity** (quote-vs-paraphrase signal) — each in `[0, 1]` with its own
confidence and diagnostics naming exactly what a heuristic could *not* verify
(e.g. `source_liveness_unverified`, `publication_date_unverified`,
`quote_accuracy_unverified`). Absence of evidence lowers confidence; it never
inflates a score.

### meaning — the Meaning Gradient

See [Meaning Gradient](#meaning-gradient) below — it is the one domain that
shipped first (v0.5.0) and keeps its pinned JSON shape.

### signal — trajectory analysis over any measurement

`coherence signal` is source-agnostic: it never asks what produced a series
or what the numbers mean, only how they move. It ships `trend` (first/second
differences, monotonicity, volatility), `pattern` (six motifs — increasing,
decreasing, plateau, spike, reversal, stair-step), `resonance` (one signed
Pearson correlation per field pair — positive is resonance, negative is
**interference**, from the same computation, not two code paths), `forecast`
(naive linear-trend-plus-recent-delta extrapolation, explicitly labeled
`"extrapolation"`, never prophecy), and `collect` (build a series file from N
measurement JSONs of any domain). See
[`docs/signal-series.md`](docs/signal-series.md) for the input schema.

### investiture — estimated micro-investiture

`coherence investiture` asks whether an artifact's meaning became a causal
imprint rather than just semantic structure. Its MVP measures only the
**estimated**, artifact-only slice: `investiture_score = meaning_density ×
agency_coupling × future_constraint × affordance`, computed by calling into
`coherence.meaning` rather than duplicating any embedding/axis logic. It
always reports `mode: "estimated"` and an explicit `missing_behavioral_outcome`
diagnostic, with `persistence_signal` / `integration_signal` /
`behavioral_effect` set to `None` — genuinely unmeasured, never a fabricated
zero.

### frames — provenance of the semantic coordinate frame

`coherence frames` makes the instrument that produced a score inspectable.
Every embedding-derived measurement now carries a `frame` block (embedding
model, endpoint, anchor set, axis/axes, projection method) — see
[`docs/envelope.md`](docs/envelope.md). `frames inspect <measurement.json>`
reports whether a measurement's provenance is complete, partial, or absent
(never an error — a v0.5.0-era JSON with no frame block at all is an entirely
ordinary input). `frames diff <a.json> <b.json>` decides whether two
measurements are frame-comparable (same gauge) or were produced by different
instruments. A mixed-frame guard is wired into the signal series loader so
comparing points measured under different frames produces a visible warning
instead of a silent, meaningless number.

## What you get

- **An agent-first CLI** cited from [teken](https://github.com/agentculture/teken)
  (`afi-cli`) — the runtime package has no third-party dependencies.
- **A mesh identity** — `culture.yaml` (`suffix` + `backend`) and the matching
  prompt file (`CLAUDE.md` for `backend: claude`).
- **The canonical guildmaster skill kit** (11 skills) under `.claude/skills/`,
  vendored cite-don't-import. See [`docs/skill-sources.md`](docs/skill-sources.md).
- **A build + deploy baseline** — pytest, lint, the agent-first rubric gate, and
  PyPI Trusted Publishing wired into GitHub Actions.

## Quickstart

```bash
uv sync
uv run pytest -n auto                 # run the test suite
uv run coherence-cli whoami  # identity from culture.yaml
uv run coherence-cli learn   # self-teaching prompt (add --json)
uv run teken cli doctor . --strict    # the agent-first rubric gate CI runs
```

## CLI

The agent-scaffold verbs below are always present, independent of which
coherence domains a fork keeps. See
[Coherence CLI examples](#coherence-cli-examples) further down for the
domain-measurement verbs (`quality`, `signal`, `investiture`, `frames`,
`assess`, `meaning`).

| Verb | What it does |
|------|--------------|
| `whoami` | Report this agent's nick, version, backend, and model from `culture.yaml`. |
| `learn` | Print a structured self-teaching prompt. |
| `explain <path>` | Markdown docs for any noun/verb path. |
| `overview` | Read-only descriptive snapshot of the agent. |
| `doctor` | Check the agent-identity invariants (prompt-file-present, backend-consistency). |
| `cli overview` | Describe the CLI surface itself. |

Every command supports `--json`. Results go to stdout, errors/diagnostics to
stderr (never mixed). Exit codes: `0` success, `1` user error, `2` environment
error, `3+` reserved.

## Meaning Gradient

**Meaning Gradient is a coherence dimension of coherence-cli, not a separate
CLI.** It ships as the `coherence meaning` noun — same binary, same `--json`
and exit-code conventions as every other verb. It asks one question: *how
strongly does this artifact constrain future interpretation and action?*

### How it scores — the anchor axis

Scoring is anchor-axis projection over sentence embeddings, with the anchor
sets shipped in-repo as editable fixtures so the whole claim stays falsifiable:

```text
axis  = mean(high-anchor embeddings) - mean(low-anchor embeddings)
score = cosine(embedding(artifact), axis), rescaled from [-1, 1] to [0, 1]
```

A parallel artifact scores `1.0`, orthogonal `0.5`, anti-parallel `0.0`. The
global `meaning` axis yields the scalar `meaning_score`; five subdimensions
each get their own high/low anchor pair:

| Subdimension | Asks |
|--------------|------|
| `consequence` | Does this change what happens next? |
| `agency` | Who can act because of this? |
| `causality` | Does this explain why something happened? |
| `affordance` | Does this reveal what action is possible? |
| `future_constraint` | Does this reduce the space of valid next actions? |

Alongside the embedding scores, three rule-based diagnostics run fully offline
(no network call, so they still work when the embed endpoint is down):
`missing_consequence`, `missing_owner`, `missing_next_action`.

### The three commands

| Command | What it does |
|---------|--------------|
| `coherence meaning score <file>` | Score one artifact → the JSON below. |
| `coherence meaning compare <before> <after>` | Signed per-subdimension deltas across a rewrite (the 2-point case). |
| `coherence meaning trend <f1> <f2> <f3> …` | Trajectory over an ordered series: first differences (f′, velocity) and second differences (f″, acceleration) of each score plus embedding drift. |

All three support `--json` and follow the CLI exit-code policy: `0` success,
`1` user-input error (missing file, or fewer than 2 files for `trend`), `2`
environment error — an unreachable embedding endpoint makes `score` exit `2`
with a hint naming `COHERENCE_EMBED_URL`, while the offline diagnostics still
run.

`coherence meaning score <file> --json` emits exactly:

```json
{
  "meaning_score": 0.73,
  "subdimensions": {
    "consequence": 0.81,
    "agency": 0.62,
    "causality": 0.78,
    "affordance": 0.69,
    "future_constraint": 0.75
  },
  "diagnostics": [
    {"code": "missing_owner", "message": "No responsible party named — name an owner (e.g. @name, 'owned by', 'assigned to')."}
  ]
}
```

Every value is in `[0, 1]`. `subdimensions` is an open map: registering a sixth
subdimension adds a key here without breaking existing consumers. As part of
the five-domain restructure, the same JSON additionally gains three top-level
keys — `domain`, `score_type`, `frame` — described in
[JSON contracts](#json-contracts--the-shared-envelope-and-the-two-speed-rule)
below. `meaning_score` and `subdimensions` never move or get renamed; the new
keys are purely additive.

### Consumer map — which field drives which decision

The score JSON is designed so a mesh consumer can act on it without human
translation. Each field maps to a concrete routing or memory decision:

| Consumer | Reads | Decision |
|----------|-------|----------|
| **colleague** | `meaning_score`, `frame` | The first wired consumer of `coherence meaning score --json`: colleague's post-loop coherence gate validates against this JSON directly, tolerating the additive `domain`/`score_type`/`frame` keys without editing its pinned fixture. |
| **steward** | `meaning_score` | Low `meaning_score` → route the artifact back for clarification / owner assignment before it flows downstream; high `meaning_score` with unclear ownership → ask steward to assign an owner. |
| **eidetic** | `subdimensions.consequence`, `subdimensions.future_constraint` | Gate memory writes: high on either → store (memory-worthy); low on both → compress or drop rather than persist. |
| **taskmaster** | `meaning_score`, `subdimensions.agency` | Prioritize the backlog: high `meaning_score` × high `agency` (someone can act) → surface for execution; low `agency` → hold, it needs an owner first. |

The `diagnostics` list is the always-available fallback: even with no embedding
endpoint, a fired `missing_consequence` / `missing_owner` / `missing_next_action`
is enough for a consumer to ask for clarification before acting.

### Scope boundary

This MVP ships scoring, comparison, and trend only. **The experiment runner,
the LLM-judge fallback, and doctor/certify integration are tracked follow-ups
with no code paths in this repo.** The committed
[`examples/experiments/issue-priority.yaml`](examples/experiments/issue-priority.yaml)
is the config *contract* for the deferred phase-3 experiment — every meaning
feature it names is already emitted by `coherence meaning score`, but nothing
executes it yet.

## JSON contracts — the shared envelope and the two-speed rule

Every measurement domain builds its output through one shared JSON contract,
defined in `coherence/schema.py` and documented in full in
[`docs/envelope.md`](docs/envelope.md). A conformant envelope has exactly
these five top-level keys:

```json
{
  "domain": "quality",
  "score_type": "rule_based_heuristic",
  "scores": {"freshness": 0.8, "provenance": 0.5, "fidelity": 0.4},
  "frame": null,
  "diagnostics": [
    {"code": "no_dateable_statements", "message": "no date or age signal found in the artifact"}
  ]
}
```

- `domain` — which domain produced this (`"quality"`, `"meaning"`, `"signal"`,
  `"investiture"`, …).
- `score_type` — the falsifiability class of the numbers in `scores`, e.g.
  `"model_relative_anchor_defined_projection"` (an embedding-anchor
  projection — gauge-dependent, comparable only within the same frame) or
  `"rule_based_heuristic"` (a deterministic text rule, no model dependency).
- `scores` — an open map of named numeric scores.
- `frame` — provenance of the measurement frame that produced `scores`; a
  `dict`, an explicit `null`, or a null-frame dict
  (`coherence.schema.null_frame`) carrying a machine-readable reason. The
  **key** is always present, even when there is nothing to attribute.
- `diagnostics` — a list of `{"code", "message"}` entries naming what the
  measurement could, and could not, verify. `[]` when there is nothing to flag.

### The two-speed adoption rule

Envelope adoption is deliberately **two-speed**, not an oversight:

- **New nouns — `quality`, `signal`, `investiture`, and the `assess`
  report — emit the full shared envelope from day one.** They have no prior
  JSON contract to protect.
- **Existing `meaning` verbs (`score`/`compare`/`trend`) keep their pinned
  v0.5.0 JSON shape** (`meaning_score`, `subdimensions`, `diagnostics` at the
  top level) **and gain only additive top-level keys** — `domain`,
  `score_type`, `frame`. Nesting `meaning_score`/`subdimensions` under a
  `scores` map is deferred to an explicitly versioned future migration; it is
  a breaking shape change and is never done implicitly as a side effect of a
  restructure.

Growing the `meaning` JSON is fine (backward compatible); reshaping it is not
— not yet, and not without its own version bump when it happens.

## Coherence CLI examples

The verb shapes below are the target CLI surface for the five-domain engine.
`quality`, `signal`, `investiture`, and `frames` are implemented as library
engines with full offline test coverage today; their `argparse` registration
as CLI nouns lands as a parallel build task alongside this restructure —
`coherence-cli cli overview` and `--help` always show what is actually wired
in your checkout. `meaning` is already registered and documented in full
above. Flags are kept minimal here; see each noun's `explain` entry (once
wired) or its module docstring for the exact flag surface.

```bash
# quality — offline, rule-based
coherence quality score <file> --json
coherence quality compare <before> <after> --json

# meaning — the Meaning Gradient (already wired; see above)
coherence meaning score <file> --json
coherence meaning compare <before> <after> --json
coherence meaning trend <f1> <f2> <f3> ... --json

# signal — trajectory analysis over any domain's series
coherence signal collect <score1.json> <score2.json> ... --json
coherence signal trend <series.json> --json
coherence signal pattern <series.json> --json
coherence signal resonance <series.json> --json
coherence signal forecast <series.json> --json

# investiture — estimated micro-investiture
coherence investiture score <file> --json
coherence investiture compare <before> <after> --json

# frames — provenance of the semantic coordinate frame
coherence frames inspect <measurement.json> --json
coherence frames diff <a.json> <b.json> --json

# assess — every applicable domain, one multi-domain report
coherence assess <file> --json
```

## Planned extensions

The following are documented, deliberate non-goals **for this restructure** —
real directions, tracked as follow-up issues, not built yet:

- **Harmonic / wave / decay / interference-as-a-family signal analyses**
  (issue #9) — `signal resonance` already reports interference as the signed
  read of one alignment metric; standalone FFT/physical-wave-style modeling
  is a separate, larger direction built only once real series data justifies it.
- **Gauge-robustness checks** (issue #10) — measuring the same artifact
  across multiple embedding models or anchor sets and reporting how stable the
  score is, needs more than one embed frame available in practice first.
- **Investiture trace** (issue #8) — real evidence of persistence,
  integration, or behavioral effect (git survival, recall events, downstream
  references), not just the artifact-only estimate shipped today.
- **Experiment runner, `doctor --dimension`, `certify --dimension`, LLM-judge
  fallback, routing-policy output** (issues #4 / #6) — the already-tracked
  meaning-gradient roadmap, untouched by this restructure.
- **Freshness half-life / staleness-date prediction** — a real "predict
  coherence" direction for the quality domain, needing longitudinal data
  before a model would be honest.

None of these have code paths in this repo; they are named here so the
five-domain positioning does not imply more than what actually ships.

## Language and falsifiability

Every score in this repo is a **model-relative, anchor-defined semantic
measurement**, declared relative to the embedding model, endpoint, and anchor
set that produced it — never treated as meaning the same thing independent of
that instrument. `signal forecast` output is explicitly labeled
extrapolation, a mechanical continuation of recent history, never a promise
about the future. Anchors are axes/observables (editable, in-repo fixtures),
not fixed truths. Accordingly, coherence-cli's output and docs deliberately
avoid:

- Framing a "signal" as a physical wave, force, or energy — see
  [Planned extensions](#planned-extensions) for why harmonic/wave modeling is
  explicitly deferred, not implied by the name.
- Any evocative, supernatural, or spiritual framing of what a score measures.
- Implying two scores mean the same thing when they weren't produced by the
  same gauge — see [JSON contracts](#json-contracts--the-shared-envelope-and-the-two-speed-rule):
  `coherence frames` exists specifically so a consumer can tell when two
  scores come from different embedding models/anchor sets and are not
  directly comparable.

## Make it your own

1. Rename the package `coherence/` and the `coherence-cli`
   CLI/dist name throughout `pyproject.toml`, the package, `tests/`,
   `sonar-project.properties`, and this `README.md`. The name is hard-coded in
   ~100 places, so list every occurrence first — see the `git grep` discovery
   command in [`CLAUDE.md`](CLAUDE.md), the authoritative rename procedure.
2. Edit `culture.yaml` with your `suffix` and `backend`.
3. Rewrite `CLAUDE.md` for your agent and run `/init`.
4. Re-vendor only the skills you need from guildmaster (see
   [`docs/skill-sources.md`](docs/skill-sources.md)).

See [`CLAUDE.md`](CLAUDE.md) for the full conventions (version-bump-every-PR,
the `cicd` PR lane, deploy setup).

## License

Apache 2.0 — see [`LICENSE`](LICENSE).
