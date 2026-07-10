"""Shared CLI-boundary helpers for the domain noun commands.

Extracted from the per-noun command modules (``quality``, ``signal``,
``investiture``, ``frames``, ``assess``), which each carried an identical copy
of the file-error → :class:`CliError` mapping, the ``--reference-date``
parsing, and the ``--json`` flag wiring. The mapping is parametrised by the
*subject* word so each noun keeps its established message wording
("artifact path" / "series path" / "measurement path").

``--json`` placement: every noun parser defines ``--json`` with a ``False``
default, and every verb subparser re-declares it for help visibility. The verb
flag is registered via :func:`add_verb_json_flag` with
``default=argparse.SUPPRESS`` so that when the flag is *absent* the subparser
does not clobber a noun-level ``--json`` already parsed into the namespace
(``coherence signal --json trend …`` must mean JSON output, same as
``coherence signal trend … --json``).
"""

from __future__ import annotations

import argparse
from datetime import date, datetime

from coherence.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, CliError

JSON_HELP = "Emit structured JSON."

DIRECTORY_REMEDIATION = "pass a path to a file, not a directory"
UNREADABLE_REMEDIATION = "check the file's permissions and that it is readable by this process"
REFERENCE_DATE_REMEDIATION = (
    "pass --reference-date in YYYY-MM-DD format, e.g. --reference-date 2026-01-15"
)

#: The file-access exceptions :func:`file_cli_error` knows how to map. Catch
#: exactly this tuple after any module-specific branches.
FILE_ERRORS = (FileNotFoundError, IsADirectoryError, UnicodeDecodeError, OSError)


def file_cli_error(
    err: BaseException,
    *,
    missing_path: str,
    subject: str = "artifact",
    encoding_subject: str | None = None,
) -> CliError:
    """Map a file-access exception to the standard :class:`CliError`.

    ``subject`` names what the path was expected to be ("artifact", "series",
    "measurement") in the missing-file remediation; ``encoding_subject``
    (defaulting to ``subject``) is the wording used in the re-save-as-UTF-8
    remediation ("artifact" vs "series file" vs "measurement file").

    Returns the :class:`CliError` for the caller to ``raise … from err`` so
    the exception chain stays at the call site.
    """
    encoding_subject = encoding_subject or subject
    if isinstance(err, FileNotFoundError):
        missing = getattr(err, "filename", None) or missing_path
        return CliError(
            code=EXIT_USER_ERROR,
            message=f"file not found: {missing}",
            remediation=f"check that the {subject} path exists and is a readable UTF-8 file",
        )
    if isinstance(err, IsADirectoryError):
        path = getattr(err, "filename", None) or missing_path
        return CliError(
            code=EXIT_USER_ERROR,
            message=f"expected a file but got a directory: {path}",
            remediation=DIRECTORY_REMEDIATION,
        )
    if isinstance(err, UnicodeDecodeError):
        return CliError(
            code=EXIT_USER_ERROR,
            message=f"file is not valid UTF-8 text: {missing_path}",
            remediation=f"re-save the {encoding_subject} as UTF-8 text",
        )
    if isinstance(err, OSError):
        path = getattr(err, "filename", None) or missing_path
        return CliError(
            code=EXIT_ENV_ERROR,
            message=f"file unreadable: {path}: {err.strerror or err}",
            remediation=UNREADABLE_REMEDIATION,
        )
    raise TypeError(f"not a file-access error: {type(err).__name__}") from err


def parse_reference_date(raw: str | None) -> date:
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
            remediation=REFERENCE_DATE_REMEDIATION,
        ) from err


def add_verb_json_flag(parser: argparse.ArgumentParser) -> None:
    """Register a verb-level ``--json`` that never clobbers the noun-level one.

    ``default=argparse.SUPPRESS`` means an absent flag leaves the namespace
    untouched, so a ``--json`` given before the verb survives subparser
    parsing; handlers keep reading ``getattr(args, "json", False)``.
    """
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=JSON_HELP)
