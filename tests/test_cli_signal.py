"""Tests for the ``coherence signal`` CLI noun (plan task t16).

The signal engines (trend/pattern/resonance/forecast/collect) are fully
offline and deterministic — no embedding dependency — so these tests drive the
REAL engines through :func:`coherence.cli.main`, writing series/measurement
JSON fixtures to ``tmp_path``.

Coverage:

* JSON verbatim pass-through for trend / pattern / resonance / forecast /
  collect.
* The three exit codes: 0 success, 1 user error (malformed series file,
  nothing forecastable), 2 environment error (unreadable file).
* The bare-noun overview and introspection surfaces.
"""

from __future__ import annotations

import json

import pytest

from coherence.cli import main


def _write_series(tmp_path, name: str = "series.json", *, domain: str = "quality") -> str:
    series = {
        "domain": domain,
        "points": [
            {"id": "p0", "index": 0, "values": {"x": 0.10, "y": 0.30}},
            {"id": "p1", "index": 1, "values": {"x": 0.20, "y": 0.20}},
            {"id": "p2", "index": 2, "values": {"x": 0.30, "y": 0.10}},
            {"id": "p3", "index": 3, "values": {"x": 0.40, "y": 0.00}},
        ],
    }
    path = tmp_path / name
    path.write_text(json.dumps(series), encoding="utf-8")
    return str(path)


# --- trend -------------------------------------------------------------------


def test_signal_trend_json(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    series_path = _write_series(tmp_path)

    rc = main(["signal", "trend", series_path, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["n"] == 4
    assert set(payload["fields"]) == {"x", "y"}
    assert payload["fields"]["x"]["monotonicity"] == "increasing"


def test_signal_trend_text(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    series_path = _write_series(tmp_path)

    rc = main(["signal", "trend", series_path])
    assert rc == 0
    out = capsys.readouterr().out
    assert "fields:" in out


def test_signal_trend_bad_series_is_user_error(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"no_points_key": True}), encoding="utf-8")

    rc = main(["signal", "trend", str(bad), "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 1


def test_signal_trend_missing_file_is_user_error(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["signal", "trend", "/no/such/series.json", "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert "file not found" in payload["message"]


def test_signal_trend_invalid_json_is_user_error(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")

    rc = main(["signal", "trend", str(bad), "--json"])
    assert rc == 1


# --- pattern -----------------------------------------------------------------


def test_signal_pattern_json(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    series_path = _write_series(tmp_path)

    rc = main(["signal", "pattern", series_path, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["n"] == 4
    assert "increasing" in payload["fields"]["x"]["motifs"]


# --- resonance ---------------------------------------------------------------


def test_signal_resonance_json(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    series_path = _write_series(tmp_path)

    rc = main(["signal", "resonance", series_path, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["pairs"]) == 1
    pair = payload["pairs"][0]
    assert {pair["a"], pair["b"]} == {"x", "y"}
    assert pair["relation"] == "interference"  # x rises while y falls


# --- forecast ----------------------------------------------------------------


def test_signal_forecast_json(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    series_path = _write_series(tmp_path)

    rc = main(["signal", "forecast", series_path, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["label"] == "extrapolation"
    assert payload["fields"]["x"]["forecast"] is not None


def test_signal_forecast_nothing_forecastable_is_user_error(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    series = {"domain": None, "points": [{"id": "p0", "index": 0, "values": {"x": 0.1}}]}
    path = tmp_path / "short.json"
    path.write_text(json.dumps(series), encoding="utf-8")

    rc = main(["signal", "forecast", str(path), "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 1
    assert payload["remediation"]


# --- collect -----------------------------------------------------------------


def test_signal_collect_json(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    m1 = tmp_path / "m1.json"
    m2 = tmp_path / "m2.json"
    m1.write_text(json.dumps({"domain": "quality", "scores": {"freshness": 0.5}}), encoding="utf-8")
    m2.write_text(json.dumps({"domain": "quality", "scores": {"freshness": 0.7}}), encoding="utf-8")

    rc = main(["signal", "collect", str(m1), str(m2), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["domain"] == "quality"
    assert len(payload["points"]) == 2
    assert payload["points"][0]["values"]["freshness"] == 0.5


def test_signal_collect_without_json_flag_still_emits_series_json(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    # collect's whole purpose is to feed the pipeline -- its output is always
    # the raw series JSON, regardless of --json (see cli/_commands/signal.py).
    m1 = tmp_path / "m1.json"
    m1.write_text(json.dumps({"domain": "quality", "scores": {"freshness": 0.5}}), encoding="utf-8")

    rc = main(["signal", "collect", str(m1)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["points"][0]["id"] == "m1.json"


def test_signal_collect_can_pipe_into_trend(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    m1 = tmp_path / "m1.json"
    m2 = tmp_path / "m2.json"
    m3 = tmp_path / "m3.json"
    for path, value in ((m1, 0.2), (m2, 0.4), (m3, 0.6)):
        path.write_text(
            json.dumps({"domain": "quality", "scores": {"freshness": value}}), encoding="utf-8"
        )

    rc = main(["signal", "collect", str(m1), str(m2), str(m3)])
    assert rc == 0
    series_json = capsys.readouterr().out
    series_path = tmp_path / "series.json"
    series_path.write_text(series_json, encoding="utf-8")

    rc = main(["signal", "trend", str(series_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["fields"]["freshness"]["monotonicity"] == "increasing"


def test_signal_collect_missing_file_is_user_error(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["signal", "collect", "/no/such/measurement.json", "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 1


def test_signal_collect_no_numeric_values_is_user_error(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    m1 = tmp_path / "m1.json"
    m1.write_text(json.dumps({"note": "no numbers here"}), encoding="utf-8")

    rc = main(["signal", "collect", str(m1)])
    assert rc == 1


# --- bare noun overview --------------------------------------------------


def test_signal_bare_prints_overview(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["signal"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# coherence signal" in out
    for verb in ("trend", "pattern", "resonance", "forecast", "collect"):
        assert verb in out


def test_signal_bare_json_overview(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["signal", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "coherence signal"


# --- explain catalog -----------------------------------------------------


@pytest.mark.parametrize("verb", ["trend", "pattern", "resonance", "forecast", "collect"])
def test_explain_signal_verb_resolves(verb: str, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["explain", "signal", verb])
    assert rc == 0
    assert capsys.readouterr().out.strip()


def test_signal_collect_non_object_json_is_user_error(tmp_path, capsys) -> None:
    """A measurement file holding valid JSON that is not an object exits 1
    with a structured error, never an unhandled AttributeError (PR #14
    review, Qodo finding 3)."""
    bad = tmp_path / "list.json"
    bad.write_text('["not", "an", "object"]', encoding="utf-8")

    rc = main(["signal", "collect", str(bad)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "list.json" in err
    assert "object" in err
