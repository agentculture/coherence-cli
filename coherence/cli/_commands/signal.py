"""``coherence signal`` — trend/pattern/resonance/forecast/collect a series.

Wires the source-agnostic series-analysis engines (:mod:`coherence.signal.trend`,
:mod:`coherence.signal.pattern`, :mod:`coherence.signal.resonance`,
:mod:`coherence.signal.forecast`, :mod:`coherence.signal.collect`) into the
CLI as a ``signal`` noun with five verbs plus a bare-noun overview, mirroring
:mod:`coherence.cli._commands.meaning`'s pattern.

* ``coherence signal trend <series.json>`` — per-field f'/f'' differences,
  monotonicity, volatility.
* ``coherence signal pattern <series.json>`` — per-field motif detection
  (increasing/decreasing/plateau/spike/reversal/stair_step).
* ``coherence signal resonance <series.json>`` — pairwise signed alignment
  between fields.
* ``coherence signal forecast <series.json>`` — naive next-point
  extrapolation per field (explicitly labelled "extrapolation", never a
  prophecy).
* ``coherence signal collect <score.json> [<score.json> ...]`` — build a
  series from N measurement JSONs of any domain; prints the series JSON to
  stdout so it can be piped straight into the other four verbs.

Accepted input
--------------
``trend``/``forecast`` accept a raw series payload (the engines call
:func:`coherence.signal.schema.load_series` themselves when given anything
other than an already-loaded ``Series``), so the CLI reads the file's raw text
and passes it straight through. ``pattern``/``resonance`` require an
already-loaded :class:`~coherence.signal.schema.Series`, so the CLI loads it
explicitly first.

``collect`` is different in kind from the other four: it does not analyze a
series, it BUILDS one, so its output is always the raw series dict (regardless
of ``--json``) — that is the whole point of the verb (piping into the other
four). ``--json`` is still accepted for interface uniformity across the noun.

Error contract
--------------
* :class:`~coherence.signal.schema.SeriesError` (malformed series — not a
  mapping, missing ``points``, unparseable JSON, ...) → ``EXIT_USER_ERROR`` (1).
* :class:`~coherence.signal.forecast.ForecastError` (not a single field has
  enough points to forecast) → ``EXIT_USER_ERROR`` (1).
* :class:`FileNotFoundError` / :class:`IsADirectoryError` /
  :class:`UnicodeDecodeError` → ``EXIT_USER_ERROR`` (1).
* A malformed JSON file passed to ``collect`` (:class:`json.JSONDecodeError`,
  raised directly by :func:`coherence.signal.collect.collect_files`, which
  does its own unwrapped ``json.loads``) → ``EXIT_USER_ERROR`` (1).
* :class:`OSError` (e.g. ``PermissionError``) → ``EXIT_ENV_ERROR`` (2).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from coherence.cli._commands._artifact_io import (
    FILE_ERRORS,
    add_verb_json_flag,
    file_cli_error,
)
from coherence.cli._commands.overview import emit_overview
from coherence.cli._errors import EXIT_USER_ERROR, CliError
from coherence.cli._output import emit_result
from coherence.signal.collect import collect_files
from coherence.signal.forecast import ForecastError, forecast
from coherence.signal.pattern import detect_patterns
from coherence.signal.resonance import resonance
from coherence.signal.schema import SeriesError, load_series
from coherence.signal.trend import trend

_SERIES_REMEDIATION = (
    'pass a well-formed series JSON: {"domain": <str|null>, "points": [...]}; '
    "see 'coherence explain signal'"
)
_FORECAST_REMEDIATION = (
    "forecasting needs at least 3 present values in some field; pass a longer series"
)
_INVALID_JSON_REMEDIATION = "check the file contains valid JSON"

_FIELDS_HEADER = "fields:"
_SERIES_FILE_HELP = "Path to the series JSON."

_VERBS = [
    "trend <series.json> — per-field f'/f'' differences, monotonicity, volatility",
    "pattern <series.json> — per-field motif detection (increasing/decreasing/"
    "plateau/spike/reversal/stair_step)",
    "resonance <series.json> — pairwise signed alignment between fields",
    "forecast <series.json> — naive next-point extrapolation per field "
    "(labelled 'extrapolation', never a prophecy)",
    "collect <score.json> [<score.json> ...] — build a series from N "
    "measurement JSONs of any domain",
]


def _guard(fn: Callable[[], dict], *, missing_path: str) -> dict:
    """Run an engine call, converting its exceptions into :class:`CliError`."""
    try:
        return fn()
    except SeriesError as err:
        raise CliError(
            code=EXIT_USER_ERROR,
            message=str(err) or "invalid series",
            remediation=_SERIES_REMEDIATION,
        ) from err
    except ForecastError as err:
        raise CliError(
            code=EXIT_USER_ERROR,
            message=str(err) or "nothing forecastable",
            remediation=_FORECAST_REMEDIATION,
        ) from err
    except json.JSONDecodeError as err:
        raise CliError(
            code=EXIT_USER_ERROR,
            message=f"file is not valid JSON: {missing_path}: {err}",
            remediation=_INVALID_JSON_REMEDIATION,
        ) from err
    except FILE_ERRORS as err:
        raise file_cli_error(
            err,
            missing_path=missing_path,
            subject="series",
            encoding_subject="series file",
        ) from err


def _read_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _trend_render(result: dict) -> str:
    lines = [f"n: {result['n']}", f"domain: {result['domain']}", "", _FIELDS_HEADER]
    for name, field in result["fields"].items():
        lines.append(
            f"  {name}: n_present={field['n_present']} "
            f"monotonicity={field['monotonicity']} volatility={field['volatility']}"
        )
    return "\n".join(lines)


def _pattern_render(result: dict) -> str:
    lines = [f"n: {result['n']}", "", _FIELDS_HEADER]
    for name, field in result["fields"].items():
        motifs = ", ".join(field["motifs"]) if field["motifs"] else "none"
        lines.append(f"  {name}: motifs=[{motifs}]")
    return "\n".join(lines)


def _resonance_render(result: dict) -> str:
    lines = ["pairs:"]
    for pair in result["pairs"]:
        lines.append(
            f"  {pair['a']} / {pair['b']}: alignment={pair['alignment']:+.3f} "
            f"({pair['relation']})"
        )
    if not result["pairs"]:
        lines.append("  none")
    return "\n".join(lines)


def _forecast_render(result: dict) -> str:
    lines = [f"n: {result['n']}", f"label: {result['label']}", "", _FIELDS_HEADER]
    for name, field in result["fields"].items():
        if field["forecast"] is None:
            lines.append(f"  {name}: not forecast ({field['reason']})")
        else:
            lines.append(f"  {name}: {field['forecast']:.3f} ({field['method']})")
    return "\n".join(lines)


def cmd_trend(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    result = _guard(lambda: trend(_read_file(args.file)), missing_path=args.file)
    emit_result(result if json_mode else _trend_render(result), json_mode=json_mode)
    return 0


def cmd_pattern(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    result = _guard(
        lambda: detect_patterns(load_series(_read_file(args.file))),
        missing_path=args.file,
    )
    emit_result(result if json_mode else _pattern_render(result), json_mode=json_mode)
    return 0


def cmd_resonance(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    result = _guard(
        lambda: resonance(load_series(_read_file(args.file))),
        missing_path=args.file,
    )
    emit_result(result if json_mode else _resonance_render(result), json_mode=json_mode)
    return 0


def cmd_forecast(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    result = _guard(lambda: forecast(_read_file(args.file)), missing_path=args.file)
    emit_result(result if json_mode else _forecast_render(result), json_mode=json_mode)
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    files = list(args.files)
    result = _guard(lambda: collect_files(files), missing_path=", ".join(files))
    # collect always emits the raw series JSON -- that IS its output, meant to
    # be piped straight into trend/pattern/resonance/forecast (see module
    # docstring). --json is accepted for uniformity but does not change this.
    emit_result(result, json_mode=True)
    return 0


def _noun_sections() -> list[dict[str, object]]:
    return [
        {"title": "Verbs", "items": list(_VERBS)},
        {
            "title": "Conventions",
            "items": [
                "trend/pattern/resonance/forecast/collect all support --json",
                "'collect' always prints the raw series JSON to stdout (its output "
                "IS the pipeline artifact for the other four verbs)",
                "exit codes: 0 success, 1 user error (bad path / malformed series / "
                "nothing forecastable), 2 environment error (file unreadable)",
            ],
        },
    ]


def _no_verb(args: argparse.Namespace) -> int:
    # `coherence signal` with no sub-verb prints the noun's overview.
    emit_overview(
        "coherence signal",
        _noun_sections(),
        json_mode=bool(getattr(args, "json", False)),
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "signal",
        help="Trend/pattern/resonance/forecast/collect a measurement series "
        "(see 'coherence signal').",
    )
    add_verb_json_flag(p)
    p.set_defaults(func=_no_verb, json=False)
    noun_sub = p.add_subparsers(dest="signal_command", parser_class=type(p))

    tr = noun_sub.add_parser(
        "trend", help="Per-field f'/f'' differences, monotonicity, and volatility."
    )
    tr.add_argument("file", help=_SERIES_FILE_HELP)
    add_verb_json_flag(tr)
    tr.set_defaults(func=cmd_trend)

    pa = noun_sub.add_parser("pattern", help="Per-field motif detection.")
    pa.add_argument("file", help=_SERIES_FILE_HELP)
    add_verb_json_flag(pa)
    pa.set_defaults(func=cmd_pattern)

    re_ = noun_sub.add_parser("resonance", help="Pairwise signed alignment between fields.")
    re_.add_argument("file", help=_SERIES_FILE_HELP)
    add_verb_json_flag(re_)
    re_.set_defaults(func=cmd_resonance)

    fo = noun_sub.add_parser(
        "forecast", help="Naive next-point extrapolation per field (labelled 'extrapolation')."
    )
    fo.add_argument("file", help=_SERIES_FILE_HELP)
    add_verb_json_flag(fo)
    fo.set_defaults(func=cmd_forecast)

    co = noun_sub.add_parser(
        "collect", help="Build a series from N measurement JSONs of any domain."
    )
    co.add_argument("files", nargs="+", help="One or more measurement JSON paths, in order.")
    add_verb_json_flag(co)
    co.set_defaults(func=cmd_collect)
