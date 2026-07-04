"""Markdown catalog for ``coherence-cli explain <path>``.

Each entry is verbatim markdown. Keys are command-path tuples. The empty tuple
and ``("coherence-cli",)`` both resolve to the root entry.

Keep bodies self-contained: an agent reading one entry should get enough
context without chaining reads.
"""

from __future__ import annotations

_ROOT = """\
# coherence-cli

A clonable template for AgentCulture mesh agents. It carries an agent-first CLI
(cited from the teken `python-cli` reference), a mesh identity (`culture.yaml` +
`CLAUDE.md`), the canonical guildmaster skill kit under `.claude/skills/`, and a
buildable/deployable package baseline. Clone it, rename the package, edit
`culture.yaml`, and you have a new agent.

## Verbs

- `coherence-cli whoami` — identity probe from `culture.yaml`.
- `coherence-cli learn` — structured self-teaching prompt.
- `coherence-cli explain <path>` — markdown docs for any noun/verb.
- `coherence-cli overview` — descriptive snapshot of the agent.
- `coherence-cli doctor` — check the agent-identity invariants.
- `coherence-cli cli overview` — describe the CLI surface.

## Exit-code policy

- `0` success
- `1` user-input error
- `2` environment / setup error
- `3+` reserved

## See also

- `coherence-cli explain whoami`
- `coherence-cli explain doctor`
"""

_WHOAMI = """\
# coherence-cli whoami

Reports the agent's identity from `culture.yaml`: nick (`suffix`), backend,
served model, and the package version. Read-only.

## Usage

    coherence-cli whoami
    coherence-cli whoami --json
"""

_LEARN = """\
# coherence-cli learn

Prints a structured self-teaching prompt covering purpose, command map,
exit-code policy, `--json` support, and the `explain` pointer.

## Usage

    coherence-cli learn
    coherence-cli learn --json
"""

_EXPLAIN = """\
# coherence-cli explain <path>

Prints markdown documentation for any noun/verb path. Unlike `--help` (terse,
positional), `explain` is global and addressable by path.

## Usage

    coherence-cli explain coherence-cli
    coherence-cli explain whoami
    coherence-cli explain --json <path>
"""

_OVERVIEW = """\
# coherence-cli overview

Read-only descriptive snapshot of the agent: identity (from `culture.yaml`), the
verb surface, and the sibling-pattern artifacts the template carries. Accepts an
ignored `target` so a stray path never hard-fails.

## Usage

    coherence-cli overview
    coherence-cli overview --json
"""

_DOCTOR = """\
# coherence-cli doctor

Checks the agent-identity invariants `steward doctor` verifies:
prompt-file-present and backend-consistency (`claude` → `CLAUDE.md`), plus a
skills-present check. Exits 1 when unhealthy.

## Usage

    coherence-cli doctor
    coherence-cli doctor --json
"""

_CLI = """\
# coherence-cli cli

Noun group for CLI-surface introspection. `cli overview` describes the CLI
itself (distinct from the global `overview`, which describes the agent).

## Usage

    coherence-cli cli overview
    coherence-cli cli overview --json
"""


_MEANING = """\
# coherence meaning

Noun group for the Meaning Gradient engine: it measures how much *meaning* a text
artifact carries — a global `meaning_score` in `[0, 1]` plus five subdimensions
(consequence, agency, causality, affordance, future_constraint) — and how that
meaning moves between versions. Bare `coherence meaning` prints this overview.

## Verbs

- `coherence meaning score <file>` — score one artifact.
- `coherence meaning compare <before> <after>` — signed before/after delta.
- `coherence meaning trend <f1> <f2> [<f3> ...]` — per-step f'/f'' across a series.

## Usage

    coherence meaning
    coherence meaning --json

## Exit codes

- `0` success
- `1` user error (bad artifact path; `trend` given fewer than 2 files)
- `2` environment error (the embedding endpoint is unreachable)

## See also

- `coherence explain meaning score`
- `coherence explain meaning compare`
- `coherence explain meaning trend`
"""

_MEANING_SCORE = """\
# coherence meaning score <file>

Scores a single artifact's Meaning Gradient. Embeds the artifact once and
projects it onto the global meaning axis plus each subdimension axis, then runs
the always-available offline diagnostics.

## Usage

    coherence meaning score path/to/artifact.md
    coherence meaning score path/to/artifact.md --json

## JSON shape

    {"meaning_score": <float 0..1>,
     "subdimensions": {"consequence": <float>, "agency": <float>,
                       "causality": <float>, "affordance": <float>,
                       "future_constraint": <float>},
     "diagnostics": [{"code": <str>, "message": <str>}, ...]}

## Exit codes

- `0` success
- `1` file not found (bad artifact path)
- `2` embedding endpoint unreachable
"""

_MEANING_COMPARE = """\
# coherence meaning compare <before> <after>

Scores two artifact versions and reports the signed `after - before` delta for
the global `meaning_score` and every subdimension (a positive delta means the
`after` artifact gained meaning on that dimension). Comparing a file with itself
yields all-zero deltas.

## Usage

    coherence meaning compare old.md new.md
    coherence meaning compare old.md new.md --json

## JSON shape

    {"before": <score(before) dict>,
     "after":  <score(after) dict>,
     "delta":  {"meaning_score": <float>,
                "subdimensions": {"consequence": <float>, ...}}}

## Exit codes

- `0` success
- `1` file not found (either artifact path is bad)
- `2` embedding endpoint unreachable
"""

_MEANING_TREND = """\
# coherence meaning trend <f1> <f2> [<f3> ...]

Takes an *ordered* series of two or more artifact versions and reports how
meaning moves across it: per-step first differences (f', velocity) and, once
there are at least three points, second differences (f'', acceleration) — for
the global `meaning_score`, each subdimension, and embedding drift. Order is
significant; differences are taken between consecutive entries.

## Usage

    coherence meaning trend v1.md v2.md v3.md
    coherence meaning trend v1.md v2.md --json

## JSON shape

    {"n": <int>, "paths": [...], "points": [...],
     "per_step_drift": [<float>, ...],
     "signals": {"meaning_score": {"first": {"values": [...], "reason": null},
                                   "second": {"values": [...]|null, "reason": ...}},
                 "consequence": {...}, ..., "drift": {...}},
     "second_difference_available": <bool>}

## Exit codes

- `0` success
- `1` fewer than 2 files supplied, or a file was not found
- `2` embedding endpoint unreachable
"""


ENTRIES: dict[tuple[str, ...], str] = {
    (): _ROOT,
    ("coherence-cli",): _ROOT,
    ("coherence",): _ROOT,
    ("whoami",): _WHOAMI,
    ("learn",): _LEARN,
    ("explain",): _EXPLAIN,
    ("overview",): _OVERVIEW,
    ("doctor",): _DOCTOR,
    ("cli",): _CLI,
    ("cli", "overview"): _CLI,
    ("meaning",): _MEANING,
    ("meaning", "score"): _MEANING_SCORE,
    ("meaning", "compare"): _MEANING_COMPARE,
    ("meaning", "trend"): _MEANING_TREND,
}
