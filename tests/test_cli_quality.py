"""Tests for the ``coherence quality`` CLI noun (plan task t16).

Quality is fully offline and deterministic (no embedding dependency), so these
tests drive the REAL engine through :func:`coherence.cli.main` — no
monkeypatching of the engine itself is needed, only of the CLI module's private
helpers for the couple of cases that need to simulate an OS-level failure
(permission denied) without depending on platform-specific chmod behaviour.

Coverage:

* JSON verbatim pass-through for score / compare, with an explicit
  ``--reference-date``.
* The three exit codes: 0 success, 1 user error (bad path, bad
  ``--reference-date``), 2 environment error (unreadable file).
* The bare-noun overview and introspection surfaces.
"""

from __future__ import annotations

import json

import pytest

from coherence.cli import main

_CITED_TEXT = (
    "As of 2026-01-01, according to https://example.com/report, latency fell "
    "42% to 118ms. See also coherence/quality/score.py."
)
_UNDATED_TEXT = "The parser module should be split into three smaller files for clarity."


# --- score -----------------------------------------------------------------


def test_quality_score_json(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    artifact = tmp_path / "a.md"
    artifact.write_text(_CITED_TEXT, encoding="utf-8")

    rc = main(["quality", "score", str(artifact), "--reference-date", "2026-07-07", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["domain"] == "quality"
    assert payload["score_type"] == "rule_based_heuristic"
    assert set(payload["scores"]) == {
        "freshness",
        "provenance",
        "fidelity",
        "freshness_confidence",
        "provenance_confidence",
        "fidelity_confidence",
    }
    assert payload["frame"]["available"] is False
    assert isinstance(payload["diagnostics"], list)


def test_quality_score_text(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    artifact = tmp_path / "a.md"
    artifact.write_text(_UNDATED_TEXT, encoding="utf-8")

    rc = main(["quality", "score", str(artifact)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "domain: quality" in out
    assert "freshness" in out


def test_quality_score_defaults_reference_date_to_today(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    # No --reference-date supplied; the CLI boundary must still supply a date
    # (never None) so age is derivable when a dateable statement is present.
    artifact = tmp_path / "a.md"
    artifact.write_text(_CITED_TEXT, encoding="utf-8")

    rc = main(["quality", "score", str(artifact), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    codes = [d["code"] for d in payload["diagnostics"]]
    assert "age_not_derivable" not in codes


def test_quality_score_bad_reference_date_is_user_error(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    artifact = tmp_path / "a.md"
    artifact.write_text(_UNDATED_TEXT, encoding="utf-8")

    rc = main(["quality", "score", str(artifact), "--reference-date", "not-a-date"])
    assert rc == 1
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert "hint:" in err


def test_quality_score_missing_file_is_user_error(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["quality", "score", "/no/such/file.md", "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 1
    assert "file not found" in payload["message"]
    assert payload["remediation"]


def test_quality_score_directory_path_is_user_error(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = tmp_path / "a_dir"
    directory.mkdir()

    rc = main(["quality", "score", str(directory), "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 1
    assert "directory" in payload["message"]


def test_quality_score_permission_error_is_env_error(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "unreadable.md"
    artifact.write_text("x", encoding="utf-8")

    def _raise(path: str) -> str:
        raise PermissionError(13, "Permission denied", path)

    monkeypatch.setattr("coherence.cli._commands.quality._read_file", _raise)

    rc = main(["quality", "score", str(artifact), "--json"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 2
    assert "unreadable" in payload["message"]


# --- compare -----------------------------------------------------------------


def test_quality_compare_json(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    before = tmp_path / "before.md"
    after = tmp_path / "after.md"
    before.write_text(_UNDATED_TEXT, encoding="utf-8")
    after.write_text(_CITED_TEXT, encoding="utf-8")

    rc = main(
        ["quality", "compare", str(before), str(after), "--reference-date", "2026-07-07", "--json"]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"before", "after", "delta"}
    assert set(payload["delta"]) == {
        "freshness",
        "provenance",
        "fidelity",
        "freshness_confidence",
        "provenance_confidence",
        "fidelity_confidence",
    }


def test_quality_compare_self_is_all_zero(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    artifact = tmp_path / "a.md"
    artifact.write_text(_CITED_TEXT, encoding="utf-8")

    rc = main(
        [
            "quality",
            "compare",
            str(artifact),
            str(artifact),
            "--reference-date",
            "2026-07-07",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert all(value == pytest.approx(0.0) for value in payload["delta"].values())


def test_quality_compare_missing_file_is_user_error(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["quality", "compare", "/no/such/before.md", "/no/such/after.md", "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 1


# --- bare noun overview ------------------------------------------------------


def test_quality_bare_prints_overview(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["quality"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# coherence quality" in out
    for verb in ("score", "compare"):
        assert verb in out


def test_quality_bare_json_overview(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["quality", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "coherence quality"
    assert payload["sections"]


# --- explain catalog ---------------------------------------------------------


def test_explain_quality_resolves(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["explain", "quality"])
    assert rc == 0
    assert "coherence quality" in capsys.readouterr().out


def test_explain_quality_score_resolves(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["explain", "quality", "score"])
    assert rc == 0
    assert "freshness" in capsys.readouterr().out
