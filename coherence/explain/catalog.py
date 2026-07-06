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


_QUALITY = """\
# coherence quality

Noun group for the offline, rule-based quality engine: it scores an artifact's
information quality along three components — freshness (is there a dateable
statement, and how old is it?), provenance (is there source attribution?), and
fidelity (verbatim quotes/figures vs. unattributed paraphrase?) — each in
`[0, 1]` with a visible confidence and diagnostics naming what a rule could NOT
verify. Fully offline and deterministic: no embeddings, no network, no
`datetime.now()` (a `--reference-date` you pass, or today by default, decides
freshness age). Bare `coherence quality` prints this overview.

## Verbs

- `coherence quality score <file>` — score one artifact's information quality.
- `coherence quality compare <before> <after>` — signed before/after quality
  delta.

## Usage

    coherence quality
    coherence quality --json
    coherence quality score artifact.md --reference-date 2026-01-15

## Exit codes

- `0` success
- `1` user error (bad artifact path; unparseable `--reference-date`)
- `2` environment error (file unreadable, e.g. a permission error)

## See also

- `coherence explain quality score`
- `coherence explain quality compare`
- `coherence explain gauge-robust score`
"""

_QUALITY_SCORE = """\
# coherence quality score <file>

Scores a single artifact's information quality: freshness, provenance,
fidelity — each a `[0, 1]` score plus its own confidence, in the shared
measurement envelope. The frame is an explicit null-frame (quality derives no
embedding measurement frame; it is rule-based, not model-relative).

## Usage

    coherence quality score path/to/artifact.md
    coherence quality score path/to/artifact.md --reference-date 2026-01-15
    coherence quality score path/to/artifact.md --json

## JSON shape

    {"domain": "quality", "score_type": "rule_based_heuristic",
     "scores": {"freshness": <float>, "provenance": <float>, "fidelity": <float>,
                "freshness_confidence": <float>, "provenance_confidence": <float>,
                "fidelity_confidence": <float>},
     "frame": {"available": false, "code": "rule_based_no_embedding_frame", "reason": <str>},
     "diagnostics": [{"code": <str>, "message": <str>}, ...]}

## Exit codes

- `0` success
- `1` file not found (bad artifact path); unparseable `--reference-date`
- `2` file unreadable (e.g. a permission error)
"""

_QUALITY_COMPARE = """\
# coherence quality compare <before> <after>

Scores two artifact versions and reports the signed `after - before` delta for
every quality component and its confidence (a positive delta means the
`after` artifact gained quality on that dimension). Comparing a file with
itself yields all-zero deltas.

## Usage

    coherence quality compare old.md new.md
    coherence quality compare old.md new.md --json

## JSON shape

    {"before": <score_text(before) envelope>,
     "after":  <score_text(after) envelope>,
     "delta":  {"freshness": <float>, "provenance": <float>, "fidelity": <float>,
                "freshness_confidence": <float>, "provenance_confidence": <float>,
                "fidelity_confidence": <float>}}

## Exit codes

- `0` success
- `1` file not found (either artifact path is bad); unparseable `--reference-date`
- `2` file unreadable (e.g. a permission error)
"""

_SIGNAL = """\
# coherence signal

Noun group for the source-agnostic series-analysis layer: it consumes an
ordered list of measurement points — each an arbitrarily named bag of numeric
values, produced by ANY domain (meaning, quality, investiture, or a
hand-assembled series) — and offers a family of engines over that one shape:
trend (first/second differences), pattern (motif detection), resonance
(pairwise alignment), forecast (naive extrapolation), and collect (build a
series from N measurement JSONs). The signal layer never branches on which
domain produced a series; a "signal" here just means "a named numeric field
tracked across an ordered series of points" — see `coherence explain
trajectory` for the sibling term describing the ordered points themselves.
Bare `coherence signal` prints this overview.

## Verbs

- `coherence signal trend <series.json>` — per-field f'/f'' differences,
  monotonicity, volatility.
- `coherence signal pattern <series.json>` — per-field motif detection
  (increasing/decreasing/plateau/spike/reversal/stair_step).
- `coherence signal resonance <series.json>` — pairwise SIGNED alignment
  between fields (positive = resonance, negative = interference).
- `coherence signal forecast <series.json>` — naive next-point extrapolation
  per field, explicitly labelled "extrapolation" — never a prophecy.
- `coherence signal collect <m1.json> <m2.json> ...` — build a series from N
  measurement JSONs of any domain; prints the series JSON to stdout so it
  pipes straight into the other four verbs.

## Usage

    coherence signal
    coherence signal collect a.json b.json c.json --json > series.json
    coherence signal trend series.json --json

## Exit codes

- `0` success
- `1` user error (bad path, malformed series, nothing forecastable)
- `2` environment error (file unreadable)

## See also

- `coherence explain signal trend`
- `coherence explain signal pattern`
- `coherence explain signal resonance`
- `coherence explain signal forecast`
- `coherence explain signal collect`
- `coherence explain field sample`
- `coherence explain trajectory`
"""

_SIGNAL_TREND = """\
# coherence signal trend <series.json>

Walks every numeric field in a loaded series and reports its per-step first
difference (f', velocity) and second difference (f'', acceleration), whether
the field trends monotonically, and a simple volatility measure (population
standard deviation of the first differences) — with no branch on what the
field means or which domain produced it. A field with fewer than 2 present
values gets a `null` first/second and a diagnostic, never a crash.

## Usage

    coherence signal trend series.json
    coherence signal trend series.json --json

## JSON shape

    {"n": <int>, "domain": <str|null>,
     "fields": {"<field>": {"n_present": <int>,
                            "first": {"values": [...]|null, "reason": <str|null>},
                            "second": {"values": [...]|null, "reason": <str|null>},
                            "monotonicity": "increasing"|"decreasing"|"constant"|"mixed"|null,
                            "volatility": <float|null>,
                            "diagnostics": [...]}, ...},
     "diagnostics": [...]}

## Exit codes

- `0` success
- `1` malformed series (not an object, missing `points`, unparseable JSON) or
  bad file path
- `2` file unreadable
"""

_SIGNAL_PATTERN = """\
# coherence signal pattern <series.json>

Detects which of six named motifs each numeric field in a series exhibits:
`increasing`, `decreasing`, `plateau`, `spike`, `reversal`, `stair_step`.
Motifs are independent per-field checks, not mutually exclusive. Needs at
least 3 present values per field to say anything about direction; shorter
fields (or a series with fewer than 3 points overall) get an
`insufficient_points` diagnostic instead of fabricated motifs.

## Usage

    coherence signal pattern series.json
    coherence signal pattern series.json --json

## JSON shape

    {"n": <int>,
     "fields": {"<field>": {"n_present": <int>, "motifs": [...],
                            "insufficient_points": <bool>}, ...},
     "diagnostics": [...]}

## Exit codes

- `0` success
- `1` malformed series or bad file path
- `2` file unreadable
"""

_SIGNAL_RESONANCE = """\
# coherence signal resonance <series.json>

Computes pairwise SIGNED alignment (Pearson correlation over shared points)
between every pair of numeric fields in a series. The sign IS the meaning:
positive alignment is labelled `"resonance"` (the fields reinforce each
other), negative is `"interference"` (they conflict), and a small band around
zero is `"neutral"`. Resonance and interference are the SAME computation read
by its sign — never two separate algorithms. A pair with too few common
points, or either field constant (zero variance), is excluded with a
diagnostic rather than given a fabricated correlation.

## Usage

    coherence signal resonance series.json
    coherence signal resonance series.json --json

## JSON shape

    {"pairs": [{"a": <field>, "b": <field>, "alignment": <float -1..1>,
               "relation": "resonance"|"interference"|"neutral", "n": <int>}, ...],
     "diagnostics": [...]}

## Exit codes

- `0` success
- `1` malformed series or bad file path
- `2` file unreadable
"""

_SIGNAL_FORECAST = """\
# coherence signal forecast <series.json>

Extrapolates each numeric field's NEXT value from its recent history — a
linear-trend-plus-recent-delta blend over the last 5 present values (clamped
to however many are available). Every forecast is explicitly labelled
`"extrapolation"`: this is a mechanical continuation of a declared frame's
recent trajectory, never a prediction or a promise about the future. A field
with fewer than 3 present values is simply not forecast (a per-field
diagnostic, not fatal); if NOT A SINGLE field in the whole series qualifies,
the command exits 1 (nothing forecastable at all).

## Usage

    coherence signal forecast series.json
    coherence signal forecast series.json --json

## JSON shape

    {"n": <int>, "domain": <str|null>, "label": "extrapolation",
     "fields": {"<field>": {"forecast": <float|null>,
                            "method": "linear_trend_recent_delta_blend"|null,
                            "window": <int|null>, "label": "extrapolation"|null,
                            "n_present": <int>, "reason": <str>}, ...},
     "diagnostics": [...]}

## Exit codes

- `0` success
- `1` malformed series, bad file path, or no field has enough points to
  forecast at all
- `2` file unreadable
"""

_SIGNAL_COLLECT = """\
# coherence signal collect <m1.json> <m2.json> ...

Builds a series from N measurement JSONs of ANY domain (quality, meaning,
investiture, or a hand-assembled measurement) by extracting numeric values
shape-driven, never domain-driven: it reads a `scores` map when present (the
shared measurement envelope), else harvests top-level numeric keys and the
numeric entries of any top-level dict of numbers. Each input file's frame
block is carried through onto its point verbatim. This verb's output IS its
purpose: the series JSON on stdout, ready to pipe straight into `coherence
signal trend`/`pattern`/`resonance`/`forecast`.

## Usage

    coherence signal collect v1-quality.json v2-quality.json v3-quality.json --json > series.json
    coherence signal trend series.json --json

## JSON shape

    {"domain": <str|null>, "points": [{"id": <str>, "index": <int>,
                                       "timestamp": null, "values": {...},
                                       "frame": <dict|null>}, ...]}

## Exit codes

- `0` success
- `1` bad file path, invalid JSON, or every input has zero extractable numeric
  values
- `2` file unreadable
"""

_INVESTITURE = """\
# coherence investiture

Noun group for estimated micro-investiture: investiture is meaning that
becomes causal — not just semantic structure (what `coherence meaning`
measures) but the strength of an artifact as a causal imprint. This engine's
MVP measures ONLY the estimated, artifact-only slice of that: a deterministic
combination of four of the meaning engine's own subdimensions
(`meaning_density * agency_coupling * future_constraint * affordance`). It
always reports `mode: "estimated"` and honestly names, via an explicit
diagnostic and explicit `null` component values, that persistence,
integration, and behavioral effect were NOT measured. No mystical language:
investiture is a falsifiable, model-relative, artifact-derived estimate —
never a literal soul. Bare `coherence investiture` prints this overview.

## Verbs

- `coherence investiture score <file>` — estimate one artifact's
  micro-investiture.
- `coherence investiture compare <before> <after>` — signed before/after
  investiture delta.

## Usage

    coherence investiture
    coherence investiture --json

## Exit codes

- `0` success
- `1` user error (bad artifact path)
- `2` environment error (the embedding endpoint is unreachable — investiture
  derives from meaning, so it shares meaning's embedding dependency)

## See also

- `coherence explain investiture score`
- `coherence explain investiture compare`
- `coherence explain gauge-robust score`
"""

_INVESTITURE_SCORE = """\
# coherence investiture score <file>

Scores one artifact's ESTIMATED micro-investiture by combining four of
meaning's own subdimensions (`meaning_density`, `agency_coupling`,
`future_constraint`, `affordance`) into `investiture_score`. Every number
comes from `coherence.meaning.score.score`, called unchanged; no
embedding/axis logic is duplicated here, and this verb raises the identical
`EmbedUnavailable`-driven exit-2 path meaning score does. `components` always
also carries `persistence_signal`/`integration_signal`/`behavioral_effect` as
explicit `null` (genuinely unmeasured, never a fabricated zero).

## Usage

    coherence investiture score path/to/artifact.md
    coherence investiture score path/to/artifact.md --json

## JSON shape

    {"investiture_score": <float 0..1>, "mode": "estimated",
     "components": {"meaning_density": <float>, "agency_coupling": <float>,
                    "future_constraint": <float>, "affordance": <float>,
                    "persistence_signal": null, "integration_signal": null,
                    "behavioral_effect": null},
     "evidence": {"source": "artifact_only", "has_history": false,
                 "has_outcome_labels": false},
     "domain": "investiture", "score_type": "estimated_micro_investiture",
     "scores": {...}, "frame": {...meaning's frame, passed through verbatim...},
     "diagnostics": [...]}

## Exit codes

- `0` success
- `1` file not found (bad artifact path)
- `2` embedding endpoint unreachable
"""

_INVESTITURE_COMPARE = """\
# coherence investiture compare <before> <after>

Scores two artifact versions and reports the signed `after - before` delta for
`investiture_score` and each of the four NUMERIC components (the three
unmeasured components have no delta — subtracting `null` would fabricate a
number for something never measured, so they are simply absent from the
delta).

## Usage

    coherence investiture compare old.md new.md
    coherence investiture compare old.md new.md --json

## JSON shape

    {"before": <investiture score(before) dict>,
     "after":  <investiture score(after) dict>,
     "delta":  {"investiture_score": <float>,
                "components": {"meaning_density": <float>, "agency_coupling": <float>,
                               "future_constraint": <float>, "affordance": <float>}}}

## Exit codes

- `0` success
- `1` file not found (either artifact path is bad)
- `2` embedding endpoint unreachable
"""

_FRAMES = """\
# coherence frames

Noun group for frame provenance: per this repo's spec, embedding-derived
scores are model-relative, anchor-defined semantic measurements — never
universal ones — so a number like `meaning_score: 0.62` is meaningless
without knowing WHICH semantic coordinate frame produced it (which embedding
model and endpoint, which anchor set, which projection method). `frames` is
the noun that inspects that provenance directly. Bare `coherence frames`
prints this overview.

## Verbs

- `coherence frames inspect <measurement.json>` — which frame produced a
  measurement, and is its provenance complete, partial, or absent?
- `coherence frames diff <a.json> <b.json>` — are two measurements
  frame-comparable (the same gauge)?

## Usage

    coherence frames
    coherence frames --json

## Exit codes

- `0` success — includes an ABSENT or PARTIAL frame; that is a normal,
  honest result, never an error
- `1` user error (bad path, invalid JSON, measurement JSON is not an object)
- `2` environment error (file unreadable)

## See also

- `coherence explain frames inspect`
- `coherence explain frames diff`
- `coherence explain semantic frame`
- `coherence explain frame provenance`
"""

_FRAMES_INSPECT = """\
# coherence frames inspect <measurement.json>

Reports the semantic coordinate frame that produced a measurement's scores,
and whether its provenance is `"complete"`, `"partial"` (some required fields
missing), or `"absent"` (no `frame` key at all — a pre-envelope/v0.5.0-era
shape — or an explicit null-frame). Absence is never an error: a v0.5.0-era
measurement, or one captured while the embedding endpoint was down, is an
entirely ordinary input, and this command exits `0` on it.

## Usage

    coherence meaning score artifact.md --json > score.json
    coherence frames inspect score.json
    coherence frames inspect score.json --json

## JSON shape

    {"status": "complete"|"partial"|"absent",
     "frame": <dict|null>, "missing_fields": [...],
     "reason": <str|null>, "code": <str|null>, "diagnostics": [...]}

## Exit codes

- `0` success (including an absent or partial frame)
- `1` bad file path, invalid JSON, or the measurement JSON is not an object
- `2` file unreadable
"""

_FRAMES_DIFF = """\
# coherence frames diff <a.json> <b.json>

Decides whether two measurements were produced by the SAME gauge — same
embedding model, same serving endpoint, same anchor set, same projection
method (`IDENTITY_FIELDS`) — and are therefore safely comparable. A difference
in any identity field means the two numbers came from genuinely different
instruments (`comparable: false`). An `axis`/`axes` or `score_type` difference
alone is reported as a `soft_differences` entry and does NOT flip
`comparable` to `false` — two measurements can share the same gauge while
projecting a different semantic axis through it. Absent frames get their own
codes (`no_provenance_to_compare` when neither side has usable provenance,
`asymmetric_frame_presence` when only one does) rather than a generic
mismatch.

## Usage

    coherence frames diff before-score.json after-score.json
    coherence frames diff before-score.json after-score.json --json

## JSON shape

    {"comparable": <bool>, "code": <str>, "message": <str>,
     "differing_fields": {"<field>": {"a": ..., "b": ...}, ...},
     "soft_differences": {"<field>": {"a": ..., "b": ...}, ...},
     "frame_a": <dict|null>, "frame_b": <dict|null>}

## Exit codes

- `0` success (including `comparable: false` — that is a normal verdict,
  never a CLI error)
- `1` bad file path, invalid JSON, or a measurement JSON is not an object
- `2` file unreadable
"""

_ASSESS = """\
# coherence assess <file>

Runs EVERY applicable coherence domain against a single artifact — quality
(always, offline), meaning (needs the embedding endpoint), investiture
(derives from meaning) — and returns ONE report naming which domains ran and
which could not, with a machine-readable reason for each. Partial
availability is a NORMAL, successful result: when the embedding endpoint is
unreachable, meaning and investiture are listed in `unavailable` (with
meaning's own offline diagnostics preserved) and this command still exits
`0` — an unreachable embedding endpoint is not treated as this command's
failure, only as a fact reported inside it.

## Usage

    coherence assess artifact.md
    coherence assess artifact.md --reference-date 2026-01-15
    coherence assess artifact.md --json

## JSON shape

    {"domain": "assess", "score_type": "multi_domain_report",
     "scores": {}, "frame": null,
     "diagnostics": [{"code": "domain_unavailable", "message": <str>}, ...],
     "artifact": <str>,
     "domains": {"quality": {...}, "meaning": {...}, "investiture": {...}},
     "unavailable": {"meaning": {"code": <str>, "reason": <str>,
                                 "offline_diagnostics": [...]},
                     "investiture": {"code": <str>, "reason": <str>}}}

## Exit codes

- `0` success — including partial availability (embedding endpoint down)
- `1` file not found (bad artifact path); unparseable `--reference-date`
- `2` file unreadable (e.g. a permission error)

## See also

- `coherence explain quality`
- `coherence explain meaning`
- `coherence explain investiture`
"""

# --- concept entries --------------------------------------------------------
#
# The catalog is otherwise command-path-only (each key is a noun/verb token
# tuple). These eight entries extend the same ``ENTRIES`` mapping with the
# frame-vocabulary CONCEPT terms coherence-cli's five-domain spec relies on,
# addressed the same way a multi-word command path is: as the tuple of
# whitespace-separated words a caller types, e.g.
# ``coherence explain semantic frame`` -> ``("semantic", "frame")``. This
# keeps concept lookups indistinguishable from command lookups to
# ``coherence.explain.resolve`` -- one flat dict, one resolution rule. The
# term "signal" is deliberately NOT duplicated here: it is already a noun
# path (``("signal",)``, see ``_SIGNAL`` above), and that entry's own text
# defines the term inline rather than shadowing it with a second entry.

_CONCEPT_SEMANTIC_FRAME = """\
# semantic frame

The coordinate system an embedding-derived score is measured IN: which
embedding model produced the vectors, which endpoint served them, which
anchor set defined the projection, and which projection method turned a raw
vector into a `[0, 1]` score. A number like `meaning_score: 0.62` only means
something relative to its semantic frame — the same artifact scored through a
different model, a different anchor set, or a different endpoint can land on
a different number without the artifact itself having changed. This repo
never claims a universal meaning axis; every embedding-derived score is
declared "model-relative, anchor-defined" (see `coherence explain
model-relative score` and `coherence explain frame provenance`).

## See also

- `coherence explain frames inspect`
- `coherence explain frame provenance`
- `coherence explain gauge-robust score`
"""

_CONCEPT_FRAME_PROVENANCE = """\
# frame provenance

The record of WHICH semantic frame produced a given measurement, carried on
the measurement's `frame` key: `embedding_model`, `embedding_endpoint`,
`anchor_set`, `axis`/`axes`, `projection_method`, `score_type`. Provenance is
never fabricated when it is unavailable — a rule-based score (e.g.
`coherence quality`) carries an explicit null-frame naming why no embedding
frame exists, and `coherence frames inspect` reports a measurement's
provenance as `"complete"`, `"partial"`, or honestly `"absent"` rather than
guessing. Two measurements are only safely comparable when their provenance
agrees on the same gauge — see `coherence frames diff`.

## See also

- `coherence explain frames inspect`
- `coherence explain frames diff`
- `coherence explain semantic frame`
"""

_CONCEPT_MODEL_RELATIVE_SCORE = """\
# model-relative score

A score whose numeric value depends on WHICH embedding model produced it —
the same text embedded through two different models can legitimately project
to two different scores, because each model defines its own vector space.
This repo's embedding-derived domains (`coherence meaning`, `coherence
investiture`) are honestly labelled `score_type:
"model_relative_anchor_defined_projection"` rather than presented as a
universal truth about the text. A model-relative score is only meaningful
alongside its frame (`coherence explain frame provenance`) and is only
directly comparable to another score produced under the identical frame
(`coherence frames diff`).

## See also

- `coherence explain semantic frame`
- `coherence explain anchor-relative score`
- `coherence explain gauge-robust score`
"""

_CONCEPT_ANCHOR_RELATIVE_SCORE = """\
# anchor-relative score

A score defined relative to a declared anchor set — the high/low example
lines a dimension's contrastive axis is built from (see
`coherence.meaning.axis`). The projection method (mean(high) - mean(low),
cosine projection) turns "where does this artifact's embedding fall between
these anchor examples" into a `[0, 1]` number — the score is meaningful only
relative to THOSE anchors, not as an absolute property of the text. Changing
the anchor set changes the axis, and therefore can change the score, even
holding the embedding model fixed. `anchor_set` is one of the identity fields
`coherence frames diff` checks before calling two scores comparable.

## See also

- `coherence explain semantic frame`
- `coherence explain model-relative score`
- `coherence explain frames diff`
"""

_CONCEPT_GAUGE_ROBUST_SCORE = """\
# gauge-robust score

A score that stays meaningful even when the underlying "gauge" (embedding
model, anchor set, projection method) shifts — as opposed to a raw
model-relative/anchor-relative score, whose absolute value is only
comparable within one fixed frame. This repo does not claim any of its
current numbers ARE gauge-robust; it claims the opposite, honestly:
`coherence meaning`/`coherence investiture` scores are explicitly
model-relative and anchor-defined, and `coherence frames diff` exists
precisely because two scores are NOT safely comparable unless their frames
match on every identity field. "Gauge-robust" names the property a future
measurement would need before it could be compared safely ACROSS frames — a
goal this repo's honesty conventions require naming explicitly rather than
assuming.

## See also

- `coherence explain semantic frame`
- `coherence explain model-relative score`
- `coherence explain frames diff`
"""

_CONCEPT_FIELD_SAMPLE = """\
# field sample

One named numeric value at one point in a `coherence signal` series — e.g.
the `meaning_score` field's value at point `v2.md`. A series is a bag of
named fields sampled across an ordered set of points; a field need not be
present at every point (see `coherence explain trajectory`), and the signal
engines (`trend`, `pattern`, `resonance`, `forecast`) each analyze one
field's present samples in series order, never fabricating a value for a
missing one. `coherence signal collect` is what turns per-artifact
measurement JSONs into field samples in the first place.

## See also

- `coherence explain signal`
- `coherence explain trajectory`
- `coherence explain signal collect`
"""

_CONCEPT_TRAJECTORY = """\
# trajectory

The ordered sequence of points a `coherence signal` series traces out for one
or more fields — what `coherence signal trend` differentiates (f'/f''),
`coherence signal pattern` names the shape of (increasing/plateau/spike/
reversal/stair_step/...), and `coherence signal forecast` extrapolates one
step past. Order is the source of truth for a trajectory's position (not a
declared `index` or a timestamp); a forecast along a trajectory is explicitly
labelled "extrapolation" — a mechanical continuation of the trajectory's
recent shape, never a prediction or a promise about where it is actually
headed.

## See also

- `coherence explain signal trend`
- `coherence explain signal pattern`
- `coherence explain signal forecast`
- `coherence explain field sample`
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
    ("quality",): _QUALITY,
    ("quality", "score"): _QUALITY_SCORE,
    ("quality", "compare"): _QUALITY_COMPARE,
    ("signal",): _SIGNAL,
    ("signal", "trend"): _SIGNAL_TREND,
    ("signal", "pattern"): _SIGNAL_PATTERN,
    ("signal", "resonance"): _SIGNAL_RESONANCE,
    ("signal", "forecast"): _SIGNAL_FORECAST,
    ("signal", "collect"): _SIGNAL_COLLECT,
    ("investiture",): _INVESTITURE,
    ("investiture", "score"): _INVESTITURE_SCORE,
    ("investiture", "compare"): _INVESTITURE_COMPARE,
    ("frames",): _FRAMES,
    ("frames", "inspect"): _FRAMES_INSPECT,
    ("frames", "diff"): _FRAMES_DIFF,
    ("assess",): _ASSESS,
    # --- concept entries (frame vocabulary; see the block above) -----------
    ("semantic", "frame"): _CONCEPT_SEMANTIC_FRAME,
    ("frame", "provenance"): _CONCEPT_FRAME_PROVENANCE,
    ("model-relative", "score"): _CONCEPT_MODEL_RELATIVE_SCORE,
    ("anchor-relative", "score"): _CONCEPT_ANCHOR_RELATIVE_SCORE,
    ("gauge-robust", "score"): _CONCEPT_GAUGE_ROBUST_SCORE,
    ("field", "sample"): _CONCEPT_FIELD_SAMPLE,
    ("trajectory",): _CONCEPT_TRAJECTORY,
}
