"""Cross-cutting CLI wiring tests for plan task t16.

Covers what doesn't belong to any single new noun's own test file:

1. ``coherence explain <path>`` resolves every new noun/verb path AND the
   eight frame-vocabulary concept terms.
2. ``cli overview`` and ``learn`` list all five domains (quality, meaning,
   signal, investiture, frames).
3. measure/analyze/assess/predict each map to at least one WORKING command
   (not just a catalog entry) — quality score (measure), signal
   trend/pattern/resonance (analyze), assess (assess), signal forecast
   (predict).
"""

from __future__ import annotations

import json

import pytest

from coherence.cli import main
from coherence.explain import known_paths

_NEW_COMMAND_PATHS = [
    ("quality",),
    ("quality", "score"),
    ("quality", "compare"),
    ("signal",),
    ("signal", "trend"),
    ("signal", "pattern"),
    ("signal", "resonance"),
    ("signal", "forecast"),
    ("signal", "collect"),
    ("investiture",),
    ("investiture", "score"),
    ("investiture", "compare"),
    ("frames",),
    ("frames", "inspect"),
    ("frames", "diff"),
    ("assess",),
]

_FRAME_VOCABULARY_TERMS = [
    ("semantic", "frame"),
    ("frame", "provenance"),
    ("model-relative", "score"),
    ("anchor-relative", "score"),
    ("gauge-robust", "score"),
    ("field", "sample"),
    ("trajectory",),
    ("signal",),  # the eighth term ("signal") is folded into the noun's own entry
]


# --- explain catalog coverage ----------------------------------------------


@pytest.mark.parametrize("path", _NEW_COMMAND_PATHS)
def test_explain_resolves_every_new_command_path(
    path: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    assert path in known_paths()
    rc = main(["explain", *path])
    assert rc == 0
    assert capsys.readouterr().out.strip()


@pytest.mark.parametrize("term", _FRAME_VOCABULARY_TERMS)
def test_explain_resolves_every_frame_vocabulary_term(
    term: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    assert term in known_paths()
    rc = main(["explain", *term])
    assert rc == 0
    assert capsys.readouterr().out.strip()


def test_frame_vocabulary_descriptions_use_honest_language(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # No mystical language anywhere in the frame-vocabulary concept entries.
    banned = ("soul", "spirit", "mystical", "magic", "sacred")
    for term in _FRAME_VOCABULARY_TERMS:
        rc = main(["explain", *term])
        assert rc == 0
        out = capsys.readouterr().out.lower()
        for word in banned:
            assert word not in out, f"{term} explain text contains banned word {word!r}"


def test_investiture_and_forecast_descriptions_use_honest_language(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["explain", "investiture"])
    assert rc == 0
    out = capsys.readouterr().out.lower()
    assert "estimated" in out
    # The entry may explicitly DISCLAIM mystical language (e.g. "never a
    # literal soul") -- that is honest language, not mystical language. What
    # must never appear is an affirmative mystical claim.
    assert "a literal soul" not in out or "never" in out
    for word in ("mystical claim", "sacred", "magic"):
        assert word not in out

    rc = main(["explain", "signal", "forecast"])
    assert rc == 0
    out = capsys.readouterr().out.lower()
    assert "extrapolation" in out
    assert "prophecy" in out or "prediction" in out


# --- overview / learn list all five domains ---------------------------------

_DOMAIN_NAMES = ("quality", "meaning", "signal", "investiture", "frames")


def test_cli_overview_lists_all_five_domains(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["cli", "overview", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    for domain in _DOMAIN_NAMES:
        assert domain in out


def test_global_overview_lists_all_five_domains(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["overview", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    for domain in _DOMAIN_NAMES:
        assert domain in out


def test_learn_lists_all_five_domains(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["learn", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    paths = [c["path"] for c in payload["commands"]]
    # ``learn``'s command map lists VERBS, not bare nouns (matching the
    # existing convention: the pre-existing "meaning" noun isn't listed bare
    # either, only its verbs) -- so check the multi-token verb paths.
    verb_paths = [path for path in _NEW_COMMAND_PATHS if len(path) > 1] + [("assess",)]
    for path in verb_paths:
        assert list(path) in paths, f"{path} missing from learn's command map"

    rc = main(["learn"])
    assert rc == 0
    out = capsys.readouterr().out
    for domain in _DOMAIN_NAMES:
        assert domain in out


# --- measure / analyze / assess / predict map to a working command ---------


def test_measure_analyze_assess_predict_each_map_to_a_working_command(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # measure -> quality score (fully offline, real engine)
    artifact = tmp_path / "a.md"
    artifact.write_text(
        "According to https://example.com, retries fell 42% as of 2026-01-01.",
        encoding="utf-8",
    )
    rc = main(["quality", "score", str(artifact), "--json"])
    assert rc == 0
    capsys.readouterr()

    # analyze -> signal trend / pattern / resonance (fully offline, real engine)
    series = tmp_path / "series.json"
    series.write_text(
        json.dumps(
            {
                "domain": "quality",
                "points": [
                    {"id": "p0", "index": 0, "values": {"x": 0.1, "y": 0.3}},
                    {"id": "p1", "index": 1, "values": {"x": 0.2, "y": 0.2}},
                    {"id": "p2", "index": 2, "values": {"x": 0.3, "y": 0.1}},
                ],
            }
        ),
        encoding="utf-8",
    )
    assert main(["signal", "trend", str(series), "--json"]) == 0
    capsys.readouterr()
    assert main(["signal", "pattern", str(series), "--json"]) == 0
    capsys.readouterr()
    assert main(["signal", "resonance", str(series), "--json"]) == 0
    capsys.readouterr()

    # predict -> signal forecast (fully offline, real engine)
    assert main(["signal", "forecast", str(series), "--json"]) == 0
    capsys.readouterr()

    # assess -> coherence assess (monkeypatched to avoid a real embedding call;
    # see tests/test_cli_assess.py for why the engine itself is not driven here)
    monkeypatch.setattr(
        "coherence.cli._commands.assess.assess",
        lambda path, **kw: {
            "domain": "assess",
            "score_type": "multi_domain_report",
            "scores": {},
            "frame": None,
            "diagnostics": [],
            "artifact": str(path),
            "domains": {},
            "unavailable": {},
        },
    )
    assert main(["assess", str(artifact), "--json"]) == 0
