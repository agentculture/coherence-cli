"""``coherence meaning`` — score/compare/trend an artifact's Meaning Gradient.

Wires the offline-testable meaning engine into the CLI as a ``meaning`` noun
with three verbs plus a bare-noun overview (mirroring the ``cli`` noun's
``_no_verb`` pattern):

* ``coherence meaning score <file>`` — one artifact's meaning gradient.
* ``coherence meaning compare <before> <after>`` — signed before/after delta.
* ``coherence meaning trend <f1> <f2> [<f3> ...]`` — per-step f'/f'' derivatives.

Every verb supports ``--json``: text mode renders a short readable summary,
``--json`` emits the engine dict verbatim.

Error contract
--------------
The dispatcher (:func:`coherence.cli._dispatch`) only maps
:class:`~coherence.cli._errors.CliError` to a meaningful exit code; any other
exception becomes an opaque exit 1. So engine exceptions are converted here:

* :class:`~coherence.meaning.EmbedUnavailable` → ``EXIT_ENV_ERROR`` (2) — the
  embedding endpoint is unreachable (an environment problem, not user input).
  Caught explicitly so it never escapes and gets mislabelled as exit 1.
* :class:`FileNotFoundError` (a bad artifact path) → ``EXIT_USER_ERROR`` (1).
* :class:`IsADirectoryError` (path is a directory, not a file) →
  ``EXIT_USER_ERROR`` (1).
* :class:`UnicodeDecodeError` (artifact is not valid UTF-8) →
  ``EXIT_USER_ERROR`` (1).
* :class:`OSError` (e.g. ``PermissionError``, or any other unreadable file) →
  ``EXIT_ENV_ERROR`` (2) — matches the documented exit-code policy in
  :mod:`coherence.cli._errors` ("2 = environment / setup error … file
  unreadable").
* ``trend`` with fewer than 2 files → ``EXIT_USER_ERROR`` (1), checked in the
  handler because argparse ``nargs='+'`` still admits a single file.
"""

from __future__ import annotations

import argparse
from typing import Callable

from coherence.cli._commands.overview import emit_overview
from coherence.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, CliError
from coherence.cli._output import emit_result
from coherence.meaning import EmbedUnavailable
from coherence.meaning.compare import compare
from coherence.meaning.score import score
from coherence.meaning.trend import trend

_EMBED_REMEDIATION = (
    "point COHERENCE_EMBED_URL (and COHERENCE_EMBED_MODEL) at a reachable "
    "OpenAI-compatible /v1/embeddings endpoint"
)
_MISSING_FILE_REMEDIATION = "check that the artifact path exists and is a readable UTF-8 file"
_DIRECTORY_REMEDIATION = "pass a path to a file, not a directory"
_ENCODING_REMEDIATION = "re-save the artifact as UTF-8 text"
_UNREADABLE_REMEDIATION = "check the file's permissions and that it is readable by this process"

# Shared across the noun's ``--json`` flag and all three verbs' ``--json`` flags
# (SonarCloud S1192 — avoid the duplicated string literal).
_JSON_HELP = "Emit structured JSON."

# The noun's own verb surface (distinct from the global overview's verb list).
_VERBS = [
    "score <file> — score one artifact's meaning gradient",
    "compare <before> <after> — signed before/after meaning delta",
    "trend <f1> <f2> [<f3> ...] — per-step f'/f'' across an ordered series",
]


def _guard(fn: Callable[[], dict], *, missing_path: str) -> dict:
    """Run an engine call, converting its exceptions into :class:`CliError`.

    ``missing_path`` is the fallback shown in a ``file not found`` (or other
    path-related) message when the raised exception carries no ``filename``
    (e.g. a test stub raising it bare).

    Order matters: :class:`IsADirectoryError` and :class:`PermissionError` are
    both subclasses of :class:`OSError`, so their handlers must come before
    the catch-all ``OSError`` branch.
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


def _fmt_scalar(value: float) -> str:
    return f"{value:.3f}"


def _fmt_delta(value: float) -> str:
    return f"{value:+.3f}"


def _fmt_series(values: list[float] | None) -> str:
    if values is None:
        return "unavailable (need >= 3 points)"
    return "[" + ", ".join(_fmt_delta(v) for v in values) + "]"


def _score_text(result: dict) -> str:
    lines = [f"meaning_score: {_fmt_scalar(result['meaning_score'])}", "", "subdimensions:"]
    for name, value in result["subdimensions"].items():
        lines.append(f"  {name}: {_fmt_scalar(value)}")
    diags = result.get("diagnostics", [])
    lines.append("")
    if diags:
        lines.append("diagnostics:")
        for diag in diags:
            lines.append(f"  [{diag['code']}] {diag['message']}")
    else:
        lines.append("diagnostics: none")
    return "\n".join(lines)


def _compare_text(result: dict) -> str:
    lines = [
        f"before meaning_score: {_fmt_scalar(result['before']['meaning_score'])}",
        f"after  meaning_score: {_fmt_scalar(result['after']['meaning_score'])}",
        f"delta  meaning_score: {_fmt_delta(result['delta']['meaning_score'])}",
        "",
        "subdimension deltas:",
    ]
    for name, value in result["delta"]["subdimensions"].items():
        lines.append(f"  {name}: {_fmt_delta(value)}")
    return "\n".join(lines)


def _trend_text(result: dict) -> str:
    lines = [f"trend over {result['n']} measurement points:"]
    for path in result["paths"]:
        lines.append(f"  {path}")
    lines.append("")
    signal = result["signals"]["meaning_score"]
    lines.append(f"meaning_score f'  (velocity):     {_fmt_series(signal['first']['values'])}")
    lines.append(f"meaning_score f'' (acceleration): {_fmt_series(signal['second']['values'])}")
    return "\n".join(lines)


def cmd_score(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    result = _guard(lambda: score(args.file), missing_path=args.file)
    emit_result(result if json_mode else _score_text(result), json_mode=json_mode)
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    result = _guard(
        lambda: compare(args.before, args.after),
        missing_path=f"{args.before} or {args.after}",
    )
    emit_result(result if json_mode else _compare_text(result), json_mode=json_mode)
    return 0


def cmd_trend(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    files = list(args.files)
    if len(files) < 2:
        # argparse nargs='+' admits a single file; a trend needs a step.
        raise CliError(
            code=EXIT_USER_ERROR,
            message="meaning trend needs at least 2 files",
            remediation="pass two or more artifact paths in series order, e.g. "
            "'coherence meaning trend v1.md v2.md'",
        )
    result = _guard(lambda: trend(files), missing_path=", ".join(files))
    emit_result(result if json_mode else _trend_text(result), json_mode=json_mode)
    return 0


def _noun_sections() -> list[dict[str, object]]:
    return [
        {"title": "Verbs", "items": list(_VERBS)},
        {
            "title": "Conventions",
            "items": [
                "every verb supports --json (emits the engine dict verbatim)",
                "exit codes: 0 success, 1 user error (bad path / <2 trend files), "
                "2 environment error (embedding endpoint unreachable)",
            ],
        },
    ]


def _no_verb(args: argparse.Namespace) -> int:
    # `coherence meaning` with no sub-verb prints the noun's overview.
    emit_overview(
        "coherence meaning",
        _noun_sections(),
        json_mode=bool(getattr(args, "json", False)),
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "meaning",
        help="Score/compare/trend an artifact's meaning gradient (see 'coherence meaning').",
    )
    p.add_argument("--json", action="store_true", help=_JSON_HELP)
    p.set_defaults(func=_no_verb, json=False)
    # `p` is a _CliArgumentParser (propagated via parser_class) so nested-verb
    # parse errors route through the structured error contract, not argparse's
    # default stderr/exit 2.
    noun_sub = p.add_subparsers(dest="meaning_command", parser_class=type(p))

    sc = noun_sub.add_parser("score", help="Score one artifact's meaning gradient.")
    sc.add_argument("file", help="Path to the artifact to score.")
    sc.add_argument("--json", action="store_true", help=_JSON_HELP)
    sc.set_defaults(func=cmd_score)

    cmp_ = noun_sub.add_parser(
        "compare",
        help="Signed before/after meaning delta between two artifact versions.",
    )
    cmp_.add_argument("before", help="Path to the earlier artifact version.")
    cmp_.add_argument("after", help="Path to the later artifact version.")
    cmp_.add_argument("--json", action="store_true", help=_JSON_HELP)
    cmp_.set_defaults(func=cmd_compare)

    tr = noun_sub.add_parser(
        "trend",
        help="Per-step f'/f'' derivatives across an ordered series of >= 2 artifacts.",
    )
    tr.add_argument(
        "files",
        nargs="+",
        help="Two or more artifact paths, in series order.",
    )
    tr.add_argument("--json", action="store_true", help=_JSON_HELP)
    tr.set_defaults(func=cmd_trend)
