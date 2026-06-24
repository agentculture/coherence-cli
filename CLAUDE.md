# CLAUDE.md — seed / bootstrap placeholder

> **This is a self-initializing seed, not a finished runtime prompt.**
> Run `/init` (or describe the agent's domain to your AI assistant) to
> re-initialize this file into a full runtime prompt, using the description
> below and the scaffolded repo as context.

## Agent

This repository hosts the **coherence-cli** agent.

## Description

Maintains information quality for agentic workflows — assesses the freshness, provenance, fidelity, and task-specific validity of claims, then refreshes or repairs degraded ones before agents consume them.

## Re-init instruction

This file is a seed. To expand it into your full runtime prompt:

1. Open this repo in Claude Code (or your preferred AI assistant).
2. Run `/init` — the assistant will read the repo, incorporate the description
   above, and replace this seed with a complete `CLAUDE.md`.
3. Commit the result.

Until you run `/init`, `coherence-cli` satisfies the `steward doctor`
`prompt-file-present` and `backend-consistency` invariants (a `CLAUDE.md`
exists and `culture.yaml` declares `backend: claude`) but the prompt is not
yet tailored to this agent's domain.

## Conventions and workflow

**Memory discipline — recall before, remember after.** This repo keeps its
eidetic memory **in-repo and public**: records resolve to
`<repo-root>/.eidetic/memory` — committed, and shared with the team and mesh
peers (the `claude` and `colleague` backends both read the same
`coherence-cli` scope), so memory travels with the repo, not a private
home-dir store. Make it a per-task habit:

- **`/recall` before you start.** Search the store for the area you're about
  to touch — prior decisions, gotchas, "have we done this before?" — so you
  build on what's already known instead of re-deriving it. Do this before
  non-trivial tasks, not just when asked.
- **`/remember` when something worth keeping surfaces.** A non-obvious
  decision and its rationale, a constraint, a fix and *why* it was needed, a
  gotcha that cost time, a fact the next session would otherwise re-learn.
  Capture it as it happens, not at the end when it's faded.

A plain `/remember` lands the note in `./.eidetic/memory` in this repo — no
flag needed (the wrappers here default to `--visibility public`; in-repo
routing needs `eidetic >= 0.10.0`, older CLIs keep records in `$HOME`). Keep
something out of the committed store only by passing `--visibility private`
(routes to `$HOME/.eidetic/memory`, never committed); `/recall` reads both
stores and merges. Don't store what the repo already records (code structure,
git history, what's already in this file or `CHANGELOG.md`) — store what you'd
have to re-derive. These are the `recall`/`remember` skills (`.claude/skills/`),
backed by the `eidetic` store.
