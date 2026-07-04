"""Tests for the ``coherence meaning`` CLI noun (plan task t8).

Every test drives the CLI through :func:`coherence.cli.main` with the meaning
engine (`score`/`compare`/`trend`) monkeypatched at the name the handler module
imported it under (``coherence.cli._commands.meaning.<fn>``), so **no network is
used** — the real embedding endpoint is never contacted.

Coverage:

* JSON verbatim pass-through for score / compare / trend.
* The three exit codes the error contract must map:
  0 success, 1 user error (bad path, <2 trend files), 2 environment error
  (``EmbedUnavailable``).
* The bare-noun overview and the explain catalog entries.
* The noun is surfaced in overview / learn / explain introspection.
"""

from __future__ import annotations

import json

import pytest

from coherence.cli import main
from coherence.meaning import EmbedUnavailable

_SUBDIMENSIONS = ("consequence", "agency", "causality", "affordance", "future_constraint")


def _fake_score(meaning: float = 0.72) -> dict:
    """A valid ``score`` engine dict — the exact three-key contract."""
    return {
        "meaning_score": meaning,
        "subdimensions": {name: 0.5 for name in _SUBDIMENSIONS},
        "diagnostics": [{"code": "hedged_claim", "message": "hedged language detected"}],
    }


def _fake_compare() -> dict:
    before = _fake_score(0.40)
    after = _fake_score(0.65)
    return {
        "before": before,
        "after": after,
        "delta": {
            "meaning_score": 0.25,
            "subdimensions": {name: 0.0 for name in _SUBDIMENSIONS},
        },
    }


def _fake_trend(paths: list[str]) -> dict:
    n = len(paths)
    return {
        "n": n,
        "paths": [str(p) for p in paths],
        "points": [_fake_score(0.5) for _ in paths],
        "per_step_drift": [0.1] * (n - 1),
        "signals": {
            "meaning_score": {
                "first": {"values": [0.1] * (n - 1), "reason": None},
                "second": {
                    "values": [0.0] * (n - 2) if n >= 3 else None,
                    "reason": None if n >= 3 else "need >= 3 points",
                },
            }
        },
        "second_difference_available": n >= 3,
    }


# --- score ---------------------------------------------------------------


def test_meaning_score_json(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "a.md"
    artifact.write_text("some artifact text", encoding="utf-8")
    monkeypatch.setattr("coherence.cli._commands.meaning.score", lambda path: _fake_score(0.81))

    rc = main(["meaning", "score", str(artifact), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["meaning_score"] == 0.81
    assert set(payload["subdimensions"]) == set(_SUBDIMENSIONS)
    assert isinstance(payload["diagnostics"], list)
    assert payload["diagnostics"][0]["code"] == "hedged_claim"


def test_meaning_score_text(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "a.md"
    artifact.write_text("x", encoding="utf-8")
    monkeypatch.setattr("coherence.cli._commands.meaning.score", lambda path: _fake_score(0.72))

    rc = main(["meaning", "score", str(artifact)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "meaning_score:" in out
    assert "consequence" in out


# --- compare -------------------------------------------------------------


def test_meaning_compare_json(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    before = tmp_path / "before.md"
    after = tmp_path / "after.md"
    before.write_text("v1", encoding="utf-8")
    after.write_text("v2", encoding="utf-8")
    monkeypatch.setattr(
        "coherence.cli._commands.meaning.compare",
        lambda b, a: _fake_compare(),
    )

    rc = main(["meaning", "compare", str(before), str(after), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"before", "after", "delta"}
    assert payload["delta"]["meaning_score"] == 0.25
    assert set(payload["delta"]["subdimensions"]) == set(_SUBDIMENSIONS)


# --- trend ---------------------------------------------------------------


def test_meaning_trend_json(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    files = []
    for name in ("f1.md", "f2.md", "f3.md"):
        f = tmp_path / name
        f.write_text(name, encoding="utf-8")
        files.append(str(f))
    monkeypatch.setattr(
        "coherence.cli._commands.meaning.trend",
        lambda paths: _fake_trend(list(paths)),
    )

    rc = main(["meaning", "trend", *files, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["n"] == 3
    assert payload["paths"] == files
    assert payload["second_difference_available"] is True


def test_meaning_trend_one_file_is_user_error(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # argparse nargs='+' admits one file; the handler must reject it (exit 1).
    # Patch trend so a leak would be obvious (it must not be called).
    called: list[int] = []
    monkeypatch.setattr(
        "coherence.cli._commands.meaning.trend",
        lambda paths: called.append(1) or _fake_trend(list(paths)),
    )
    f = tmp_path / "only.md"
    f.write_text("solo", encoding="utf-8")

    rc = main(["meaning", "trend", str(f)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "at least 2 files" in err
    assert "hint:" in err
    assert called == []


# --- error mapping -------------------------------------------------------


def test_meaning_score_missing_file_is_user_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(path: str) -> dict:
        raise FileNotFoundError(2, "No such file or directory", path)

    monkeypatch.setattr("coherence.cli._commands.meaning.score", _raise)

    rc = main(["meaning", "score", "/no/such/file", "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 1
    assert "file not found" in payload["message"]
    assert payload["remediation"]


def test_meaning_score_directory_path_is_user_error(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "a_dir"
    directory.mkdir()

    def _raise(path: str) -> dict:
        raise IsADirectoryError(21, "Is a directory", path)

    monkeypatch.setattr("coherence.cli._commands.meaning.score", _raise)

    rc = main(["meaning", "score", str(directory), "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 1
    assert "directory" in payload["message"]
    assert str(directory) in payload["message"]
    assert payload["remediation"]


def test_meaning_score_non_utf8_file_is_user_error(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "bad_encoding.md"
    artifact.write_bytes(b"\xff\xfe\x00\x01")

    def _raise(path: str) -> dict:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr("coherence.cli._commands.meaning.score", _raise)

    rc = main(["meaning", "score", str(artifact), "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 1
    assert "not valid UTF-8" in payload["message"]
    assert str(artifact) in payload["message"]
    assert payload["remediation"]


def test_meaning_score_permission_error_is_env_error(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "unreadable.md"
    artifact.write_text("x", encoding="utf-8")

    def _raise(path: str) -> dict:
        raise PermissionError(13, "Permission denied", path)

    monkeypatch.setattr("coherence.cli._commands.meaning.score", _raise)

    rc = main(["meaning", "score", str(artifact), "--json"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 2
    assert "unreadable" in payload["message"]
    assert str(artifact) in payload["message"]
    assert payload["remediation"]


def test_meaning_score_embed_unavailable_is_env_error(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "a.md"
    artifact.write_text("x", encoding="utf-8")

    def _raise(path: str) -> dict:
        raise EmbedUnavailable("cannot reach /v1/embeddings")

    monkeypatch.setattr("coherence.cli._commands.meaning.score", _raise)

    rc = main(["meaning", "score", str(artifact)])
    assert rc == 2
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert "hint:" in err
    assert "COHERENCE_EMBED_URL" in err


def test_meaning_compare_embed_unavailable_is_env_error(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    before = tmp_path / "before.md"
    after = tmp_path / "after.md"
    before.write_text("v1", encoding="utf-8")
    after.write_text("v2", encoding="utf-8")

    def _raise(b: str, a: str) -> dict:
        raise EmbedUnavailable("down")

    monkeypatch.setattr("coherence.cli._commands.meaning.compare", _raise)

    rc = main(["meaning", "compare", str(before), str(after)])
    assert rc == 2


# --- bare noun overview --------------------------------------------------


def test_meaning_bare_prints_overview(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["meaning"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# coherence meaning" in out
    for verb in ("score", "compare", "trend"):
        assert verb in out


def test_meaning_bare_json_overview(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["meaning", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "coherence meaning"
    assert payload["sections"]


# --- explain catalog -----------------------------------------------------


def test_explain_meaning_resolves(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["explain", "meaning"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip()
    assert "coherence meaning" in out


def test_explain_meaning_score_resolves(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["explain", "meaning", "score"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip()
    assert "meaning_score" in out


# --- introspection surfaces mention the noun -----------------------------


def test_introspection_surfaces_mention_meaning(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["overview", "--json"])
    assert rc == 0
    assert "meaning" in capsys.readouterr().out

    rc = main(["learn", "--json"])
    assert rc == 0
    learn_payload = json.loads(capsys.readouterr().out)
    paths = [c["path"] for c in learn_payload["commands"]]
    assert ["meaning", "score"] in paths
    assert ["meaning", "compare"] in paths
    assert ["meaning", "trend"] in paths

    rc = main(["explain", "coherence-cli"])
    assert rc == 0
    # Root explain lists verbs; the meaning noun is reachable via its own entry.
    rc = main(["explain", "meaning", "trend"])
    assert rc == 0
    assert "meaning" in capsys.readouterr().out
