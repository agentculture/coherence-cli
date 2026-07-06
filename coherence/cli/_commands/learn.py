"""``coherence-cli learn`` — the learnability affordance.

Prints a structured self-teaching prompt. Must satisfy the agent-first rubric:
>=200 chars and mention purpose, command map, exit codes, --json, and explain.
"""

from __future__ import annotations

import argparse

from coherence import __version__
from coherence.cli._output import emit_result

_TEXT = """\
coherence-cli — a clonable template for AgentCulture mesh agents.

Purpose
-------
Scaffold for a new Culture mesh agent: an agent-first CLI (cited from the teken
`python-cli` reference), an identity (culture.yaml + CLAUDE.md), the canonical
guildmaster skill kit under .claude/skills/, and a deploy/CI baseline. Clone it,
rename the package, and edit culture.yaml to mint a new agent.

Commands
--------
  coherence-cli whoami             Identity from culture.yaml.
  coherence-cli learn              This self-teaching prompt.
  coherence-cli explain <path>...  Markdown docs for any noun/verb path.
  coherence-cli overview           Descriptive snapshot of the agent.
  coherence-cli doctor             Check the agent-identity invariants.
  coherence-cli cli overview       Describe the CLI surface itself.
  coherence meaning score <file>   Score an artifact's meaning gradient.
  coherence meaning compare <a> <b>  Signed before/after meaning delta.
  coherence meaning trend <f>...   Per-step f'/f'' across a series.
  coherence quality score <file>   Score an artifact's information quality.
  coherence quality compare <a> <b>  Signed before/after quality delta.
  coherence signal trend <s.json>  Per-field f'/f'' across a series.
  coherence signal pattern <s.json>  Per-field motif detection.
  coherence signal resonance <s.json>  Pairwise signed alignment between fields.
  coherence signal forecast <s.json>  Naive next-point extrapolation per field.
  coherence signal collect <m>...  Build a series from N measurement JSONs.
  coherence investiture score <file>  Score an artifact's estimated micro-investiture.
  coherence investiture compare <a> <b>  Signed before/after investiture delta.
  coherence frames inspect <m.json>  Report the frame behind a measurement.
  coherence frames diff <a> <b>   Are two measurements frame-comparable?
  coherence assess <file>         Run every applicable domain on an artifact.

Machine-readable output
-----------------------
Every command supports --json. Errors in JSON mode emit
{"code", "message", "remediation"} to stderr. Stdout and stderr never mix.

Exit-code policy
----------------
  0 success
  1 user-input error (bad flag, bad path, missing arg)
  2 environment / setup error
  3+ reserved

More detail
-----------
  coherence-cli explain coherence-cli
"""


def _as_json_payload() -> dict[str, object]:
    return {
        "tool": "coherence-cli",
        "version": __version__,
        "purpose": "Clonable scaffold for a new AgentCulture mesh agent.",
        "commands": [
            {"path": ["whoami"], "summary": "Identity probe from culture.yaml."},
            {"path": ["learn"], "summary": "Self-teaching prompt."},
            {"path": ["explain"], "summary": "Markdown docs by path."},
            {"path": ["overview"], "summary": "Descriptive snapshot of the agent."},
            {"path": ["doctor"], "summary": "Check the agent-identity invariants."},
            {"path": ["cli", "overview"], "summary": "Describe the CLI surface."},
            {"path": ["meaning", "score"], "summary": "Score an artifact's meaning gradient."},
            {"path": ["meaning", "compare"], "summary": "Signed before/after meaning delta."},
            {"path": ["meaning", "trend"], "summary": "Per-step f'/f'' across a series."},
            {"path": ["quality", "score"], "summary": "Score an artifact's information quality."},
            {"path": ["quality", "compare"], "summary": "Signed before/after quality delta."},
            {"path": ["signal", "trend"], "summary": "Per-field f'/f'' across a series."},
            {"path": ["signal", "pattern"], "summary": "Per-field motif detection."},
            {
                "path": ["signal", "resonance"],
                "summary": "Pairwise signed alignment between fields.",
            },
            {
                "path": ["signal", "forecast"],
                "summary": "Naive next-point extrapolation per field.",
            },
            {
                "path": ["signal", "collect"],
                "summary": "Build a series from N measurement JSONs.",
            },
            {
                "path": ["investiture", "score"],
                "summary": "Score an artifact's estimated micro-investiture.",
            },
            {
                "path": ["investiture", "compare"],
                "summary": "Signed before/after investiture delta.",
            },
            {
                "path": ["frames", "inspect"],
                "summary": "Report the frame that produced a measurement.",
            },
            {"path": ["frames", "diff"], "summary": "Are two measurements frame-comparable?"},
            {
                "path": ["assess"],
                "summary": "Run every applicable coherence domain on an artifact.",
            },
        ],
        "exit_codes": {
            "0": "success",
            "1": "user-input error",
            "2": "environment/setup error",
        },
        "json_support": True,
        "explain_pointer": "coherence-cli explain <path>",
    }


def cmd_learn(args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        emit_result(_as_json_payload(), json_mode=True)
    else:
        emit_result(_TEXT, json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "learn",
        help="Print a structured self-teaching prompt for agent consumers.",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_learn)
