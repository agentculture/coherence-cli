"""``coherence assess <file>`` — run every applicable coherence domain.

Wires the multi-domain report engine (:mod:`coherence.assess`) into the CLI as
a single global verb (not a noun group — there is exactly one thing to do:
assess an artifact), following the same registration pattern as ``overview``/
``doctor``/``whoami`` in :mod:`coherence.cli._commands.overview`.

``coherence assess <file>`` runs quality (always), meaning (needs the
embedding endpoint), and investiture (derives from meaning) against a single
artifact and returns one report naming which domains ran and which did not.

Partial availability is success, not failure
----------------------------------------------
:func:`coherence.assess.assess` never raises
:class:`~coherence.meaning.EmbedUnavailable` — it catches that internally for
both the meaning and investiture sub-calls and lists the affected domain(s) in
the report's ``unavailable`` map instead (see that module's docstring). So an
unreachable embedding endpoint is NOT an environment error at this CLI
boundary: the command still exits ``0``, with the report itself naming what
could not run and why. Only genuine input/IO errors reading the artifact map
to a non-zero exit here.

Reference date
--------------
Accepts the same optional ``--reference-date YYYY-MM-DD`` flag as ``coherence
quality`` (threaded into quality's freshness scoring inside the report);
defaults to today when omitted -- see
:mod:`coherence.cli._commands.quality` for the rationale.

Error contract
--------------
* :class:`FileNotFoundError` (a bad artifact path) → ``EXIT_USER_ERROR`` (1).
* :class:`IsADirectoryError` → ``EXIT_USER_ERROR`` (1).
* :class:`UnicodeDecodeError` → ``EXIT_USER_ERROR`` (1).
* :class:`OSError` (e.g. ``PermissionError``) → ``EXIT_ENV_ERROR`` (2).
* An unparseable ``--reference-date`` → ``EXIT_USER_ERROR`` (1).
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from typing import Callable

from coherence.assess import assess
from coherence.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, CliError
from coherence.cli._output import emit_result

_MISSING_FILE_REMEDIATION = "check that the artifact path exists and is a readable UTF-8 file"
_DIRECTORY_REMEDIATION = "pass a path to a file, not a directory"
_ENCODING_REMEDIATION = "re-save the artifact as UTF-8 text"
_UNREADABLE_REMEDIATION = "check the file's permissions and that it is readable by this process"
_REFERENCE_DATE_REMEDIATION = (
    "pass --reference-date in YYYY-MM-DD format, e.g. --reference-date 2026-01-15"
)

_JSON_HELP = "Emit structured JSON."
_REFERENCE_DATE_HELP = (
    "Reference date (YYYY-MM-DD) for quality's freshness scoring. Defaults to today."
)


def _guard(fn: Callable[[], dict], *, missing_path: str) -> dict:
    """Run the assess engine, converting file I/O exceptions into :class:`CliError`.

    No :class:`~coherence.meaning.EmbedUnavailable` branch here on purpose:
    :func:`coherence.assess.assess` catches that internally (see module
    docstring), so it never escapes to this boundary.
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


def _render(result: dict) -> str:
    lines = [f"artifact: {result['artifact']}", "", "domains:"]
    for name in result["domains"]:
        lines.append(f"  {name}: available")
    for name, info in result["unavailable"].items():
        lines.append(f"  {name}: unavailable ({info['reason']})")
    diags = result.get("diagnostics", [])
    lines.append("")
    if diags:
        lines.append("diagnostics:")
        for diag in diags:
            lines.append(f"  [{diag['code']}] {diag['message']}")
    else:
        lines.append("diagnostics: none")
    return "\n".join(lines)


def cmd_assess(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    reference_date = _parse_reference_date(getattr(args, "reference_date", None))
    result = _guard(
        lambda: assess(args.file, reference_date=reference_date),
        missing_path=args.file,
    )
    emit_result(result if json_mode else _render(result), json_mode=json_mode)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "assess",
        help="Run every applicable coherence domain on an artifact "
        "(see 'coherence explain assess').",
    )
    p.add_argument("file", help="Path to the artifact to assess.")
    p.add_argument("--reference-date", dest="reference_date", help=_REFERENCE_DATE_HELP)
    p.add_argument("--json", action="store_true", help=_JSON_HELP)
    p.set_defaults(func=cmd_assess)
