# coherence-cli

Maintains information quality for agentic workflows — assesses the freshness, provenance, fidelity, and task-specific validity of claims, then refreshes or repairs degraded ones before agents consume them.

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

### Reference deployment

The lobes gateway serves an `embedder` role, discoverable via `GET /capabilities`
(lobes-cli >= 0.38 advertises a client-reachable endpoint per role). Consumers
such as colleague resolve the endpoint from lobes and inject
`COHERENCE_EMBED_URL` / `COHERENCE_EMBED_MODEL` when armed.

Each meaning score is a model-relative, anchor-defined measurement: the
embedding model and anchors constitute the score's reference frame (gauge).
Scores are not universal meaning — they are semantic measurements relative to the
chosen model and anchor set (issues #10, #11).

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
subdimension adds a key here without breaking existing consumers.

### Consumer map — which field drives which decision

The score JSON is designed so a mesh consumer can act on it without human
translation. Each field maps to a concrete routing or memory decision:

| Consumer | Reads | Decision |
|----------|-------|----------|
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
