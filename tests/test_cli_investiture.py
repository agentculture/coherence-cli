"""Tests for the ``coherence investiture`` CLI noun (plan task t16).

Investiture derives every number from :func:`coherence.meaning.score.score`,
so it shares meaning's embedding dependency. Every test here drives the CLI
through :func:`coherence.cli.main` with the investiture engine
(``score``/``compare``) monkeypatched at the name the handler module imported
it under (``coherence.cli._commands.investiture.<fn>``) — exactly the pattern
``tests/test_meaning_cli.py`` uses — so **no network is used**.

Coverage:

* JSON verbatim pass-through for score / compare.
* The three exit codes: 0 success, 1 user error (bad path), 2 environment
  error (``EmbedUnavailable``, with a hint naming ``COHERENCE_EMBED_URL``).
* The bare-noun overview and introspection surfaces.
"""

from __future__ import annotations

import json

import pytest

from coherence.cli import main
from coherence.meaning import EmbedUnavailable

_NUMERIC_COMPONENTS = ("meaning_density", "agency_coupling", "future_constraint", "affordance")


def _fake_score(investiture_score: float = 0.42) -> dict:
    components: dict = {name: 0.5 for name in _NUMERIC_COMPONENTS}
    components.update(
        {"persistence_signal": None, "integration_signal": None, "behavioral_effect": None}
    )
    return {
        "domain": "investiture",
        "score_type": "estimated_micro_investiture",
        "scores": {
            **{name: 0.5 for name in _NUMERIC_COMPONENTS},
            "investiture_score": investiture_score,
        },
        "frame": {"available": False, "code": "embed_endpoint_unreachable", "reason": "n/a"},
        "diagnostics": [{"code": "missing_behavioral_outcome", "message": "not measured"}],
        "investiture_score": investiture_score,
        "mode": "estimated",
        "components": components,
        "evidence": {"source": "artifact_only", "has_history": False, "has_outcome_labels": False},
    }


def _fake_compare() -> dict:
    before = _fake_score(0.20)
    after = _fake_score(0.55)
    return {
        "before": before,
        "after": after,
        "delta": {
            "investiture_score": 0.35,
            "components": {name: 0.0 for name in _NUMERIC_COMPONENTS},
        },
    }


# --- score -------------------------------------------------------------------


def test_investiture_score_json(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "a.md"
    artifact.write_text("some artifact text", encoding="utf-8")
    monkeypatch.setattr("coherence.cli._commands.investiture.score", lambda path: _fake_score(0.81))

    rc = main(["investiture", "score", str(artifact), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["investiture_score"] == 0.81
    assert payload["mode"] == "estimated"
    assert set(_NUMERIC_COMPONENTS) <= set(payload["components"])
    assert payload["components"]["persistence_signal"] is None


def test_investiture_score_text(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "a.md"
    artifact.write_text("x", encoding="utf-8")
    monkeypatch.setattr("coherence.cli._commands.investiture.score", lambda path: _fake_score(0.5))

    rc = main(["investiture", "score", str(artifact)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "investiture_score:" in out
    assert "mode: estimated" in out


def test_investiture_score_missing_file_is_user_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(path: str) -> dict:
        raise FileNotFoundError(2, "No such file or directory", path)

    monkeypatch.setattr("coherence.cli._commands.investiture.score", _raise)

    rc = main(["investiture", "score", "/no/such/file", "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 1
    assert "file not found" in payload["message"]


def test_investiture_score_directory_path_is_user_error(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "a_dir"
    directory.mkdir()

    def _raise(path: str) -> dict:
        raise IsADirectoryError(21, "Is a directory", path)

    monkeypatch.setattr("coherence.cli._commands.investiture.score", _raise)

    rc = main(["investiture", "score", str(directory), "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert "directory" in payload["message"]


def test_investiture_score_embed_unavailable_is_env_error(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "a.md"
    artifact.write_text("x", encoding="utf-8")

    def _raise(path: str) -> dict:
        raise EmbedUnavailable("cannot reach /v1/embeddings")

    monkeypatch.setattr("coherence.cli._commands.investiture.score", _raise)

    rc = main(["investiture", "score", str(artifact)])
    assert rc == 2
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert "hint:" in err
    assert "COHERENCE_EMBED_URL" in err


# --- compare -----------------------------------------------------------------


def test_investiture_compare_json(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    before = tmp_path / "before.md"
    after = tmp_path / "after.md"
    before.write_text("v1", encoding="utf-8")
    after.write_text("v2", encoding="utf-8")
    monkeypatch.setattr("coherence.cli._commands.investiture.compare", lambda b, a: _fake_compare())

    rc = main(["investiture", "compare", str(before), str(after), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"before", "after", "delta"}
    assert payload["delta"]["investiture_score"] == 0.35
    assert set(_NUMERIC_COMPONENTS) == set(payload["delta"]["components"])


def test_investiture_compare_embed_unavailable_is_env_error(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    before = tmp_path / "before.md"
    after = tmp_path / "after.md"
    before.write_text("v1", encoding="utf-8")
    after.write_text("v2", encoding="utf-8")

    def _raise(b: str, a: str) -> dict:
        raise EmbedUnavailable("down")

    monkeypatch.setattr("coherence.cli._commands.investiture.compare", _raise)

    rc = main(["investiture", "compare", str(before), str(after)])
    assert rc == 2


# --- bare noun overview --------------------------------------------------


def test_investiture_bare_prints_overview(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["investiture"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# coherence investiture" in out
    for verb in ("score", "compare"):
        assert verb in out


def test_investiture_bare_json_overview(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["investiture", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "coherence investiture"


# --- explain catalog -----------------------------------------------------


def test_explain_investiture_resolves(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["explain", "investiture"])
    assert rc == 0
    assert "estimated" in capsys.readouterr().out


def test_explain_investiture_score_resolves(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["explain", "investiture", "score"])
    assert rc == 0
    assert "investiture_score" in capsys.readouterr().out
