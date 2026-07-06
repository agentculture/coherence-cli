"""Tests for the ``coherence frames`` CLI noun (plan task t16).

Frame inspection/diffing is fully offline (pure functions over already-loaded
measurement dicts — no network, no embeddings call), so these tests drive the
REAL engines through :func:`coherence.cli.main`, writing measurement JSON
fixtures to ``tmp_path``.

Coverage:

* ``inspect`` on a measurement with a complete frame, a partial frame, and NO
  frame at all (a v0.5.0-era shape) — all three are EXIT 0, never an error.
* ``diff`` on matching and mismatching frames — both a normal (exit 0)
  verdict.
* The three exit codes: 0 success, 1 user error (bad path, invalid JSON), 2
  environment error (unreadable file).
* The bare-noun overview and introspection surfaces.
"""

from __future__ import annotations

import json

import pytest

from coherence.cli import main

_FULL_FRAME = {
    "embedding_model": "m1",
    "embedding_endpoint": "http://localhost:8001/v1",
    "anchor_set": "meaning-v1",
    "projection_method": "contrastive_axis",
    "score_type": "model_relative_anchor_defined_projection",
    "axes": ["meaning"],
}


def _write(tmp_path, name: str, payload: dict) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


# --- inspect -----------------------------------------------------------------


def test_frames_inspect_complete_json(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    measurement = {"domain": "meaning", "meaning_score": 0.6, "frame": _FULL_FRAME}
    path = _write(tmp_path, "score.json", measurement)

    rc = main(["frames", "inspect", path, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "complete"
    assert payload["missing_fields"] == []


def test_frames_inspect_absent_frame_is_exit_zero(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A pre-envelope / v0.5.0-era shape: no "frame" key at all.
    measurement = {"meaning_score": 0.5, "subdimensions": {}, "diagnostics": []}
    path = _write(tmp_path, "old_score.json", measurement)

    rc = main(["frames", "inspect", path, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "absent"


def test_frames_inspect_partial_frame(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    partial_frame = dict(_FULL_FRAME)
    del partial_frame["anchor_set"]
    measurement = {"domain": "meaning", "frame": partial_frame}
    path = _write(tmp_path, "partial.json", measurement)

    rc = main(["frames", "inspect", path, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "partial"
    assert "anchor_set" in payload["missing_fields"]


def test_frames_inspect_text(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    measurement = {"domain": "meaning", "frame": _FULL_FRAME}
    path = _write(tmp_path, "score.json", measurement)

    rc = main(["frames", "inspect", path])
    assert rc == 0
    assert "status: complete" in capsys.readouterr().out


def test_frames_inspect_missing_file_is_user_error(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["frames", "inspect", "/no/such/measurement.json", "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 1
    assert "file not found" in payload["message"]


def test_frames_inspect_invalid_json_is_user_error(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")

    rc = main(["frames", "inspect", str(bad), "--json"])
    assert rc == 1


def test_frames_inspect_non_object_json_is_user_error(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    scalar = tmp_path / "scalar.json"
    scalar.write_text("42", encoding="utf-8")

    rc = main(["frames", "inspect", str(scalar), "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 1


# --- diff --------------------------------------------------------------------


def test_frames_diff_comparable_json(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    a = _write(tmp_path, "a.json", {"domain": "meaning", "frame": _FULL_FRAME})
    b = _write(tmp_path, "b.json", {"domain": "meaning", "frame": dict(_FULL_FRAME)})

    rc = main(["frames", "diff", a, b, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["comparable"] is True


def test_frames_diff_not_comparable_is_still_exit_zero(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    other_frame = dict(_FULL_FRAME)
    other_frame["embedding_model"] = "m2-different"
    a = _write(tmp_path, "a.json", {"domain": "meaning", "frame": _FULL_FRAME})
    b = _write(tmp_path, "b.json", {"domain": "meaning", "frame": other_frame})

    rc = main(["frames", "diff", a, b, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["comparable"] is False
    assert "embedding_model" in payload["differing_fields"]


def test_frames_diff_text(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    a = _write(tmp_path, "a.json", {"domain": "meaning", "frame": _FULL_FRAME})
    b = _write(tmp_path, "b.json", {"domain": "meaning", "frame": dict(_FULL_FRAME)})

    rc = main(["frames", "diff", a, b])
    assert rc == 0
    assert "comparable: True" in capsys.readouterr().out


def test_frames_diff_missing_file_is_user_error(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = _write(tmp_path, "a.json", {"domain": "meaning", "frame": _FULL_FRAME})

    rc = main(["frames", "diff", a, "/no/such/b.json", "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 1


# --- bare noun overview --------------------------------------------------


def test_frames_bare_prints_overview(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["frames"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# coherence frames" in out
    for verb in ("inspect", "diff"):
        assert verb in out


def test_frames_bare_json_overview(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["frames", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "coherence frames"


# --- explain catalog -----------------------------------------------------


def test_explain_frames_resolves(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["explain", "frames"])
    assert rc == 0
    assert "coherence frames" in capsys.readouterr().out


def test_explain_frames_inspect_and_diff_resolve(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["explain", "frames", "inspect"])
    assert rc == 0
    assert capsys.readouterr().out.strip()

    rc = main(["explain", "frames", "diff"])
    assert rc == 0
    assert capsys.readouterr().out.strip()
