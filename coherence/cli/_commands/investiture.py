"""``coherence investiture`` — score/compare an artifact's estimated
micro-investiture.

Wires the offline-testable investiture engine (:mod:`coherence.investiture.score`,
:mod:`coherence.investiture.compare`) into the CLI as an ``investiture`` noun
with two verbs plus a bare-noun overview, mirroring
:mod:`coherence.cli._commands.meaning` almost exactly — investiture derives
every number from :func:`coherence.meaning.score.score`, so it shares the same
embedding dependency and the same :class:`~coherence.meaning.EmbedUnavailable`
exit-2 behaviour.

* ``coherence investiture score <file>`` — one artifact's estimated
  micro-investiture.
* ``coherence investiture compare <before> <after>`` — signed before/after
  investiture delta.

Every verb supports ``--json``: text mode renders a short readable summary,
``--json`` emits the engine dict verbatim.

Error contract
--------------
Identical to :mod:`coherence.cli._commands.meaning` (investiture calls into
the same meaning engine, so it raises the same exceptions):

* :class:`~coherence.meaning.EmbedUnavailable` → ``EXIT_ENV_ERROR`` (2) — the
  embedding endpoint is unreachable.
* :class:`FileNotFoundError` → ``EXIT_USER_ERROR`` (1).
* :class:`IsADirectoryError` → ``EXIT_USER_ERROR`` (1).
* :class:`UnicodeDecodeError` → ``EXIT_USER_ERROR`` (1).
* :class:`OSError` (e.g. ``PermissionError``) → ``EXIT_ENV_ERROR`` (2).
"""

from __future__ import annotations

import argparse
from typing import Callable

from coherence.cli._commands.overview import emit_overview
from coherence.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, CliError
from coherence.cli._output import emit_result
from coherence.investiture.compare import compare
from coherence.investiture.score import score
from coherence.meaning import EmbedUnavailable

_EMBED_REMEDIATION = (
    "point COHERENCE_EMBED_URL (and COHERENCE_EMBED_MODEL) at a reachable "
    "OpenAI-compatible /v1/embeddings endpoint"
)
_MISSING_FILE_REMEDIATION = "check that the artifact path exists and is a readable UTF-8 file"
_DIRECTORY_REMEDIATION = "pass a path to a file, not a directory"
_ENCODING_REMEDIATION = "re-save the artifact as UTF-8 text"
_UNREADABLE_REMEDIATION = "check the file's permissions and that it is readable by this process"

_JSON_HELP = "Emit structured JSON."

_VERBS = [
    "score <file> — score one artifact's estimated micro-investiture",
    "compare <before> <after> — signed before/after investiture delta",
]


def _guard(fn: Callable[[], dict], *, missing_path: str) -> dict:
    """Run an engine call, converting its exceptions into :class:`CliError`.

    Identical shape to :func:`coherence.cli._commands.meaning._guard` — see
    that function's docstring for the exact branch ordering rationale.
    """
    try:
        return fn()
    except EmbedUnavailable as err:
        raise CliError(
            code=EXIT_ENV_ERROR,
            message=str(err) or "embedding endpoint unavailable",
            remediation=_EMBED_REMEDIATION,
        ) from err
    except FileNotFoundError as err:
        missing = getattr(err, "filename", None) or missing_path
        raise CliError(
            code=EXIT_USER_ERROR,
            message=f"file not found: {missing}",
            remediation=_MISSING_FILE_REMEDIATION,
        ) from err
    except IsADirectoryError as err:
        path = getattr(err, "filename", None) or missing_path
        raise CliError(
            code=EXIT_USER_ERROR,
            message=f"expected a file but got a directory: {path}",
            remediation=_DIRECTORY_REMEDIATION,
        ) from err
    except UnicodeDecodeError as err:
        raise CliError(
            code=EXIT_USER_ERROR,
            message=f"file is not valid UTF-8 text: {missing_path}",
            remediation=_ENCODING_REMEDIATION,
        ) from err
    except OSError as err:
        path = getattr(err, "filename", None) or missing_path
        raise CliError(
            code=EXIT_ENV_ERROR,
            message=f"file unreadable: {path}: {err.strerror or err}",
            remediation=_UNREADABLE_REMEDIATION,
        ) from err


def _fmt(value: float | None) -> str:
    return "unmeasured" if value is None else f"{value:.3f}"


def _score_render(result: dict) -> str:
    lines = [
        f"investiture_score: {_fmt(result['investiture_score'])}",
        f"mode: {result['mode']}",
        "",
        "components:",
    ]
    for name, value in result["components"].items():
        lines.append(f"  {name}: {_fmt(value)}")
    diags = result.get("diagnostics", [])
    lines.append("")
    if diags:
        lines.append("diagnostics:")
        for diag in diags:
            lines.append(f"  [{diag['code']}] {diag['message']}")
    else:
        lines.append("diagnostics: none")
    return "\n".join(lines)


def _compare_render(result: dict) -> str:
    delta = result["delta"]
    lines = [f"delta investiture_score: {delta['investiture_score']:+.3f}", "", "component deltas:"]
    for name, value in delta["components"].items():
        lines.append(f"  {name}: {value:+.3f}")
    return "\n".join(lines)


def cmd_score(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    result = _guard(lambda: score(args.file), missing_path=args.file)
    emit_result(result if json_mode else _score_render(result), json_mode=json_mode)
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    result = _guard(
        lambda: compare(args.before, args.after),
        missing_path=f"{args.before} or {args.after}",
    )
    emit_result(result if json_mode else _compare_render(result), json_mode=json_mode)
    return 0


def _noun_sections() -> list[dict[str, object]]:
    return [
        {"title": "Verbs", "items": list(_VERBS)},
        {
            "title": "Conventions",
            "items": [
                "every verb supports --json (emits the engine dict verbatim)",
                "investiture is ESTIMATED from artifact structure only (mode: "
                "'estimated'); persistence/integration/behavioral effect are "
                "honestly reported as not measured, never fabricated",
                "exit codes: 0 success, 1 user error (bad path), "
                "2 environment error (embedding endpoint unreachable)",
            ],
        },
    ]


def _no_verb(args: argparse.Namespace) -> int:
    # `coherence investiture` with no sub-verb prints the noun's overview.
    emit_overview(
        "coherence investiture",
        _noun_sections(),
        json_mode=bool(getattr(args, "json", False)),
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "investiture",
        help="Score/compare an artifact's estimated micro-investiture "
        "(see 'coherence investiture').",
    )
    p.add_argument("--json", action="store_true", help=_JSON_HELP)
    p.set_defaults(func=_no_verb, json=False)
    noun_sub = p.add_subparsers(dest="investiture_command", parser_class=type(p))

    sc = noun_sub.add_parser("score", help="Score one artifact's estimated micro-investiture.")
    sc.add_argument("file", help="Path to the artifact to score.")
    sc.add_argument("--json", action="store_true", help=_JSON_HELP)
    sc.set_defaults(func=cmd_score)

    cmp_ = noun_sub.add_parser(
        "compare",
        help="Signed before/after investiture delta between two artifact versions.",
    )
    cmp_.add_argument("before", help="Path to the earlier artifact version.")
    cmp_.add_argument("after", help="Path to the later artifact version.")
    cmp_.add_argument("--json", action="store_true", help=_JSON_HELP)
    cmp_.set_defaults(func=cmd_compare)
