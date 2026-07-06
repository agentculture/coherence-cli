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
from typing import Callable

from coherence.assess import assess
from coherence.cli._commands._artifact_io import (
    FILE_ERRORS,
    add_verb_json_flag,
    file_cli_error,
    parse_reference_date,
)
from coherence.cli._output import emit_result

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
    except FILE_ERRORS as err:
        raise file_cli_error(err, missing_path=missing_path, subject="artifact") from err


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
    reference_date = parse_reference_date(getattr(args, "reference_date", None))
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
    add_verb_json_flag(p)
    p.set_defaults(func=cmd_assess)
