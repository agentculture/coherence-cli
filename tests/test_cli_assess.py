"""Tests for the ``coherence assess`` global verb (plan task t16).

``coherence.assess.assess`` derives from meaning/investiture, so it shares
their embedding dependency; unlike them, it never lets
:class:`~coherence.meaning.EmbedUnavailable` escape — it catches it internally
for both the meaning and investiture sub-calls and reports partial
availability instead (see ``coherence/assess.py``'s module docstring). The
partial-availability tests here monkeypatch the CLI module's imported
``assess`` name directly (the same pattern ``tests/test_meaning_cli.py`` uses
for ``score``/``compare``) rather than attempting a real embed call — a
keyword default (``embed_fn: EmbedFn = embed_texts``) binds to the real
function object at def-time, so patching the source module attribute would be
inert for it (see ``tests/conftest.py``).

The missing-file / bad-path tests drive the REAL engine: ``assess()`` reads
the artifact file FIRST, before ever attempting an embedding call, so a bad
path fails offline without needing to touch the embed layer at all.

Coverage:

* Partial availability (embedding endpoint down) is EXIT 0, never 1/2.
* Full availability (all three domains ran) is EXIT 0.
* Exit 1 for a missing/bad artifact path or an unparseable ``--reference-date``.
* Exit 2 for an unreadable file.
"""

from __future__ import annotations

import json

import pytest

from coherence.cli import main


def _fake_partial_report(path, **_kwargs) -> dict:
    return {
        "domain": "assess",
        "score_type": "multi_domain_report",
        "scores": {},
        "frame": None,
        "diagnostics": [
            {
                "code": "domain_unavailable",
                "message": "meaning unavailable: embedding endpoint unreachable",
            },
            {
                "code": "domain_unavailable",
                "message": "investiture unavailable: derives from meaning, which is unavailable",
            },
        ],
        "artifact": str(path),
        "domains": {
            "quality": {
                "domain": "quality",
                "score_type": "rule_based_heuristic",
                "scores": {"freshness": 0.1},
                "frame": {
                    "available": False,
                    "code": "rule_based_no_embedding_frame",
                    "reason": "n/a",
                },
                "diagnostics": [],
            }
        },
        "unavailable": {
            "meaning": {
                "code": "embed_endpoint_unreachable",
                "reason": "embedding endpoint unreachable",
            },
            "investiture": {
                "code": "embed_endpoint_unreachable",
                "reason": "derives from meaning, which is unavailable",
            },
        },
    }


def _fake_full_report(path, **_kwargs) -> dict:
    report = _fake_partial_report(path)
    report["domains"]["meaning"] = {"meaning_score": 0.6, "subdimensions": {}, "diagnostics": []}
    report["domains"]["investiture"] = {"investiture_score": 0.3}
    report["unavailable"] = {}
    report["diagnostics"] = []
    return report


# --- partial / full availability ---------------------------------------------


def test_assess_partial_availability_is_exit_zero(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "a.md"
    artifact.write_text("some text", encoding="utf-8")
    monkeypatch.setattr("coherence.cli._commands.assess.assess", _fake_partial_report)

    rc = main(["assess", str(artifact), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "quality" in payload["domains"]
    assert "meaning" in payload["unavailable"]
    assert "investiture" in payload["unavailable"]


def test_assess_full_availability_is_exit_zero(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "a.md"
    artifact.write_text("some text", encoding="utf-8")
    monkeypatch.setattr("coherence.cli._commands.assess.assess", _fake_full_report)

    rc = main(["assess", str(artifact), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload["domains"]) == {"quality", "meaning", "investiture"}
    assert payload["unavailable"] == {}


def test_assess_text_mode(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "a.md"
    artifact.write_text("some text", encoding="utf-8")
    monkeypatch.setattr("coherence.cli._commands.assess.assess", _fake_partial_report)

    rc = main(["assess", str(artifact)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "quality: available" in out
    assert "meaning: unavailable" in out


def test_assess_reference_date_is_threaded(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict = {}

    def _capture(path, *, reference_date=None, **_kwargs) -> dict:
        seen["reference_date"] = reference_date
        return _fake_partial_report(path)

    artifact = tmp_path / "a.md"
    artifact.write_text("some text", encoding="utf-8")
    monkeypatch.setattr("coherence.cli._commands.assess.assess", _capture)

    rc = main(["assess", str(artifact), "--reference-date", "2026-01-15", "--json"])
    assert rc == 0
    assert seen["reference_date"].isoformat() == "2026-01-15"


# --- error mapping (real engine; file errors happen before any embed call) --


def test_assess_missing_file_is_user_error(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["assess", "/no/such/artifact.md", "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 1
    assert "file not found" in payload["message"]


def test_assess_directory_path_is_user_error(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    directory = tmp_path / "a_dir"
    directory.mkdir()

    rc = main(["assess", str(directory), "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert "directory" in payload["message"]


def test_assess_bad_reference_date_is_user_error(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    artifact = tmp_path / "a.md"
    artifact.write_text("x", encoding="utf-8")

    rc = main(["assess", str(artifact), "--reference-date", "nope"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "hint:" in err


def test_assess_permission_error_is_env_error(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "unreadable.md"
    artifact.write_text("x", encoding="utf-8")

    def _raise(path, **_kwargs) -> dict:
        raise PermissionError(13, "Permission denied", path)

    monkeypatch.setattr("coherence.cli._commands.assess.assess", _raise)

    rc = main(["assess", str(artifact), "--json"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 2


# --- explain catalog -----------------------------------------------------


def test_explain_assess_resolves(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["explain", "assess"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "coherence assess" in out
    assert "every applicable" in out.lower()
