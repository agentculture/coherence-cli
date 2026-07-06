"""``coherence quality`` — score/compare an artifact's information quality.

Wires the offline, rule-based quality engine (:mod:`coherence.quality.score`,
:mod:`coherence.quality.compare`) into the CLI as a ``quality`` noun with two
verbs plus a bare-noun overview (mirroring the ``meaning`` noun's pattern in
:mod:`coherence.cli._commands.meaning`):

* ``coherence quality score <file>`` — one artifact's information quality
  (freshness/provenance/fidelity).
* ``coherence quality compare <before> <after>`` — signed before/after
  quality delta.

Every verb supports ``--json``: text mode renders a short readable summary,
``--json`` emits the shared measurement envelope verbatim.

Reference date
--------------
Both verbs accept an optional ``--reference-date YYYY-MM-DD`` flag. The
underlying engine (:func:`coherence.quality.score.score_text`) never calls
``datetime.now()`` — it takes a ``date`` (or ``None``) and lets the caller
decide. This is the CLI boundary that decision belongs to: when
``--reference-date`` is omitted, *today* is supplied (never ``None``), so
freshness age is always derivable when a dateable statement is present.

Error contract
--------------
Quality is fully offline (no embedding dependency), so there is no
:class:`~coherence.meaning.EmbedUnavailable` exit-2 path here — only file I/O
errors map to a non-zero exit, mirroring :mod:`coherence.cli._commands.meaning`:

* :class:`FileNotFoundError` (a bad artifact path) → ``EXIT_USER_ERROR`` (1).
* :class:`IsADirectoryError` (path is a directory, not a file) →
  ``EXIT_USER_ERROR`` (1).
* :class:`UnicodeDecodeError` (artifact is not valid UTF-8) →
  ``EXIT_USER_ERROR`` (1).
* :class:`OSError` (e.g. ``PermissionError``) → ``EXIT_ENV_ERROR`` (2).
* An unparseable ``--reference-date`` → ``EXIT_USER_ERROR`` (1).
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from coherence.cli._commands.overview import emit_overview
from coherence.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, CliError
from coherence.cli._output import emit_result
from coherence.quality.compare import compare
from coherence.quality.score import score_text

_MISSING_FILE_REMEDIATION = "check that the artifact path exists and is a readable UTF-8 file"
_DIRECTORY_REMEDIATION = "pass a path to a file, not a directory"
_ENCODING_REMEDIATION = "re-save the artifact as UTF-8 text"
_UNREADABLE_REMEDIATION = "check the file's permissions and that it is readable by this process"
_REFERENCE_DATE_REMEDIATION = (
    "pass --reference-date in YYYY-MM-DD format, e.g. --reference-date 2026-01-15"
)

_JSON_HELP = "Emit structured JSON."
_REFERENCE_DATE_HELP = (
    "Reference date (YYYY-MM-DD) to compute freshness age against. Defaults to today."
)

_VERBS = [
    "score <file> — score one artifact's information quality " "(freshness/provenance/fidelity)",
    "compare <before> <after> — signed before/after quality delta",
]


def _guard(fn: Callable[[], dict], *, missing_path: str) -> dict:
    """Run an engine call, converting its exceptions into :class:`CliError`.

    Mirrors :func:`coherence.cli._commands.meaning._guard` minus the
    :class:`~coherence.meaning.EmbedUnavailable` branch — quality has no
    embedding dependency, so it never raises that exception.
    """
    try:
        return fn()
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


def _parse_reference_date(raw: str | None) -> date:
    """Parse ``--reference-date``, defaulting to today when omitted.

    This IS the CLI boundary the engine docstrings point to: the library layer
    never calls ``datetime.now()``, so today's date is supplied here, once,
    rather than inside the engine.
    """
    if raw is None:
        return date.today()
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as err:
        raise CliError(
            code=EXIT_USER_ERROR,
            message=f"invalid --reference-date: {raw!r} (expected YYYY-MM-DD)",
            remediation=_REFERENCE_DATE_REMEDIATION,
        ) from err


def _read_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _fmt(value: float) -> str:
    return f"{value:.3f}"


def _score_render(result: dict) -> str:
    lines = [
        f"domain: {result['domain']}",
        f"score_type: {result['score_type']}",
        "",
        "scores:",
    ]
    for name, value in result["scores"].items():
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
    lines = ["quality delta:"]
    for name, value in result["delta"].items():
        lines.append(f"  {name}: {value:+.3f}")
    return "\n".join(lines)


def cmd_score(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    reference_date = _parse_reference_date(getattr(args, "reference_date", None))
    result = _guard(
        lambda: score_text(_read_file(args.file), reference_date=reference_date),
        missing_path=args.file,
    )
    emit_result(result if json_mode else _score_render(result), json_mode=json_mode)
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    reference_date = _parse_reference_date(getattr(args, "reference_date", None))
    result = _guard(
        lambda: compare(args.before, args.after, reference_date=reference_date),
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
                "every verb supports --json (emits the shared measurement envelope verbatim)",
                "--reference-date YYYY-MM-DD (optional; defaults to today) controls "
                "freshness age",
                "exit codes: 0 success, 1 user error (bad path / bad --reference-date), "
                "2 environment error (file unreadable)",
            ],
        },
    ]


def _no_verb(args: argparse.Namespace) -> int:
    # `coherence quality` with no sub-verb prints the noun's overview.
    emit_overview(
        "coherence quality",
        _noun_sections(),
        json_mode=bool(getattr(args, "json", False)),
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "quality",
        help="Score/compare an artifact's information quality (see 'coherence quality').",
    )
    p.add_argument("--json", action="store_true", help=_JSON_HELP)
    p.set_defaults(func=_no_verb, json=False)
    noun_sub = p.add_subparsers(dest="quality_command", parser_class=type(p))

    sc = noun_sub.add_parser("score", help="Score one artifact's information quality.")
    sc.add_argument("file", help="Path to the artifact to score.")
    sc.add_argument("--reference-date", dest="reference_date", help=_REFERENCE_DATE_HELP)
    sc.add_argument("--json", action="store_true", help=_JSON_HELP)
    sc.set_defaults(func=cmd_score)

    cmp_ = noun_sub.add_parser(
        "compare",
        help="Signed before/after quality delta between two artifact versions.",
    )
    cmp_.add_argument("before", help="Path to the earlier artifact version.")
    cmp_.add_argument("after", help="Path to the later artifact version.")
    cmp_.add_argument("--reference-date", dest="reference_date", help=_REFERENCE_DATE_HELP)
    cmp_.add_argument("--json", action="store_true", help=_JSON_HELP)
    cmp_.set_defaults(func=cmd_compare)
