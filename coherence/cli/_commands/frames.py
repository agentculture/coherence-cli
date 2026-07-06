"""``coherence frames`` — inspect/diff the semantic frame behind a measurement.

Wires the frame-provenance engines (:mod:`coherence.frames.inspect`,
:mod:`coherence.frames.diff`) into the CLI as a ``frames`` noun with two verbs
plus a bare-noun overview, mirroring :mod:`coherence.cli._commands.meaning`'s
pattern.

* ``coherence frames inspect <measurement.json>`` — which semantic coordinate
  frame produced a measurement's scores, and is its provenance complete,
  partial, or absent?
* ``coherence frames diff <a.json> <b.json>`` — are two measurements
  frame-comparable (the same gauge), or would comparing their numbers mix
  instruments?

Both verbs read an already-produced measurement JSON file (e.g. the output of
``coherence meaning score``, ``coherence quality score``, ``coherence
investiture score``, ...) — no network, no embeddings call.

Absent provenance is not an error
----------------------------------
A measurement with no ``frame`` key at all (a pre-envelope / v0.5.0-era shape)
or an explicit null-frame is an entirely ordinary input for ``inspect``:
:func:`coherence.frames.inspect.inspect_measurement` never raises for it, it
reports ``status: "absent"``. The CLI exits ``0`` in that case, never ``1``.

Error contract
--------------
* :class:`FileNotFoundError` / :class:`IsADirectoryError` /
  :class:`UnicodeDecodeError` → ``EXIT_USER_ERROR`` (1).
* Invalid JSON (:class:`json.JSONDecodeError`) → ``EXIT_USER_ERROR`` (1).
* A measurement JSON that isn't an object (:class:`TypeError`, raised by
  :func:`~coherence.frames.inspect.inspect_measurement` when handed a non-mapping)
  → ``EXIT_USER_ERROR`` (1).
* :class:`OSError` (e.g. ``PermissionError``) → ``EXIT_ENV_ERROR`` (2).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from coherence.cli._commands.overview import emit_overview
from coherence.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, CliError
from coherence.cli._output import emit_result
from coherence.frames.diff import diff_frames
from coherence.frames.inspect import inspect_measurement

_MISSING_FILE_REMEDIATION = "check that the measurement path exists and is a readable UTF-8 file"
_DIRECTORY_REMEDIATION = "pass a path to a file, not a directory"
_ENCODING_REMEDIATION = "re-save the measurement file as UTF-8 text"
_UNREADABLE_REMEDIATION = "check the file's permissions and that it is readable by this process"
_INVALID_JSON_REMEDIATION = "check the file contains valid JSON"
_NOT_AN_OBJECT_REMEDIATION = (
    "pass a measurement JSON object (e.g. the output of 'coherence meaning score')"
)

_JSON_HELP = "Emit structured JSON."

_VERBS = [
    "inspect <measurement.json> — which frame produced a measurement, and is "
    "its provenance complete, partial, or absent",
    "diff <a.json> <b.json> — are two measurements frame-comparable (same gauge)",
]


def _guard(fn: Callable[[], dict], *, missing_path: str) -> dict:
    """Run an engine call, converting its exceptions into :class:`CliError`."""
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
    except json.JSONDecodeError as err:
        raise CliError(
            code=EXIT_USER_ERROR,
            message=f"file is not valid JSON: {missing_path}: {err}",
            remediation=_INVALID_JSON_REMEDIATION,
        ) from err
    except TypeError as err:
        raise CliError(
            code=EXIT_USER_ERROR,
            message=f"measurement JSON must be an object: {missing_path}: {err}",
            remediation=_NOT_AN_OBJECT_REMEDIATION,
        ) from err
    except OSError as err:
        path = getattr(err, "filename", None) or missing_path
        raise CliError(
            code=EXIT_ENV_ERROR,
            message=f"file unreadable: {path}: {err.strerror or err}",
            remediation=_UNREADABLE_REMEDIATION,
        ) from err


def _load_measurement(path: str) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text)


def _inspect_render(result: dict) -> str:
    lines = [f"status: {result['status']}"]
    if result["missing_fields"]:
        lines.append(f"missing_fields: {', '.join(result['missing_fields'])}")
    if result["reason"]:
        lines.append(f"reason: {result['reason']}")
    if result["code"]:
        lines.append(f"code: {result['code']}")
    diags = result.get("diagnostics", [])
    lines.append("")
    if diags:
        lines.append("diagnostics:")
        for diag in diags:
            lines.append(f"  [{diag['code']}] {diag['message']}")
    else:
        lines.append("diagnostics: none")
    return "\n".join(lines)


def _diff_render(result: dict) -> str:
    lines = [
        f"comparable: {result['comparable']}",
        f"code: {result['code']}",
        f"{result['message']}",
    ]
    if result["differing_fields"]:
        lines.append("")
        lines.append("differing_fields:")
        for name, values in result["differing_fields"].items():
            lines.append(f"  {name}: a={values['a']!r} b={values['b']!r}")
    if result["soft_differences"]:
        lines.append("")
        lines.append("soft_differences:")
        for name, values in result["soft_differences"].items():
            lines.append(f"  {name}: a={values['a']!r} b={values['b']!r}")
    return "\n".join(lines)


def cmd_inspect(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    result = _guard(
        lambda: inspect_measurement(_load_measurement(args.file)),
        missing_path=args.file,
    )
    emit_result(result if json_mode else _inspect_render(result), json_mode=json_mode)
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    result = _guard(
        lambda: diff_frames(_load_measurement(args.a), _load_measurement(args.b)),
        missing_path=f"{args.a} or {args.b}",
    )
    emit_result(result if json_mode else _diff_render(result), json_mode=json_mode)
    return 0


def _noun_sections() -> list[dict[str, object]]:
    return [
        {"title": "Verbs", "items": list(_VERBS)},
        {
            "title": "Conventions",
            "items": [
                "every verb supports --json (emits the engine dict verbatim)",
                "absent/partial frame provenance is a normal result, never an "
                "error -- 'inspect' exits 0 even when a measurement predates the "
                "frame block entirely",
                "exit codes: 0 success, 1 user error (bad path / invalid JSON / "
                "not an object), 2 environment error (file unreadable)",
            ],
        },
    ]


def _no_verb(args: argparse.Namespace) -> int:
    # `coherence frames` with no sub-verb prints the noun's overview.
    emit_overview(
        "coherence frames",
        _noun_sections(),
        json_mode=bool(getattr(args, "json", False)),
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "frames",
        help="Inspect/diff the semantic frame behind a measurement (see 'coherence frames').",
    )
    p.add_argument("--json", action="store_true", help=_JSON_HELP)
    p.set_defaults(func=_no_verb, json=False)
    noun_sub = p.add_subparsers(dest="frames_command", parser_class=type(p))

    ins = noun_sub.add_parser(
        "inspect", help="Report the frame that produced a measurement and its provenance state."
    )
    ins.add_argument("file", help="Path to the measurement JSON.")
    ins.add_argument("--json", action="store_true", help=_JSON_HELP)
    ins.set_defaults(func=cmd_inspect)

    di = noun_sub.add_parser("diff", help="Decide whether two measurements are frame-comparable.")
    di.add_argument("a", help="Path to the first measurement JSON.")
    di.add_argument("b", help="Path to the second measurement JSON.")
    di.add_argument("--json", action="store_true", help=_JSON_HELP)
    di.set_defaults(func=cmd_diff)
