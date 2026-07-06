"""Offline schema/contract tests for the meaning engine and its CLI wire format.

Every test here runs fully offline through the *real* engine
(``score``/``compare``/``trend``) with a synthetic, deterministic ``embed_fn``
(``tests/_meaning_synthetic.py``) — no recorded-vectors file and no network.
The point is not the numbers but the *shape*: the exact top-level keys, the five
named subdimensions, unit-range floats, the diagnostics list-of-dict form, and
the documented ``compare``/``trend`` structures. It also drives the real CLI per
verb and json.loads its stdout to confirm the wire format equals the contract,
and checks that ``compare`` and ``trend`` agree on a shared two-point series.

Why the CLI tests inject ``embed_fn`` instead of patching the module embedder
-----------------------------------------------------------------------------
The engine's default ``embed_fn`` is a *keyword default* bound to the real
:func:`coherence.meaning.embed.embed_texts` **object** at def-time. Rebinding
the module attribute ``coherence.meaning.score.embed_texts`` afterwards is inert
for that default (verified: the CLI would still hit the network and exit 2). So
these tests patch the handler-level engine symbol
(``coherence.cli._commands.meaning.score`` etc.) with a ``functools.partial``
that injects the synthetic embedder into the real engine — the real
score/compare/trend code runs end-to-end, only the network embedder is swapped.
"""

from __future__ import annotations

import json
from functools import partial
from pathlib import Path

import pytest

from coherence.cli import main
from coherence.meaning.axis import DIMENSIONS
from coherence.meaning.compare import compare
from coherence.meaning.score import score
from coherence.meaning.trend import trend

from ._meaning_synthetic import synthetic_embed_fn

_SUBDIMENSIONS = ("consequence", "agency", "causality", "affordance", "future_constraint")

# The three additive top-level keys the two-speed envelope adds to the meaning
# outputs (see docs/envelope.md). These shape assertions are relaxed to
# *tolerate* those additions while pinning the pre-existing keys exactly; the
# additive keys' presence/values are asserted in tests/test_meaning_envelope_keys.py.
_ADDITIVE_KEYS = {"domain", "score_type", "frame"}

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "meaning"
_FILE_A = _FIXTURES / "auth_middleware.high.txt"
_FILE_B = _FIXTURES / "auth_middleware.low.txt"
_FILE_C = _FIXTURES / "payment_webhook.high.txt"


# --- reusable schema assertions ------------------------------------------


def _assert_unit_float(value: object, label: str) -> None:
    assert isinstance(value, float), f"{label} is {type(value).__name__}, expected float"
    assert 0.0 <= value <= 1.0, f"{label}={value} out of [0, 1]"


def _assert_score_schema(payload: dict) -> None:
    """A ``score``-shaped dict: exact keys, five subdimensions, unit floats, diags.

    Additive-tolerant: a top-level ``score`` result gains the three envelope
    keys, while the clean before/after blocks nested in a ``compare`` result do
    not — stripping the additive keys must leave exactly the pinned v0.5.0 keys
    in both cases.
    """
    assert set(payload) - _ADDITIVE_KEYS == {"meaning_score", "subdimensions", "diagnostics"}
    _assert_unit_float(payload["meaning_score"], "meaning_score")

    subs = payload["subdimensions"]
    assert isinstance(subs, dict)
    assert set(subs) == set(_SUBDIMENSIONS)
    assert list(subs) == list(_SUBDIMENSIONS), "subdimensions must be in DIMENSIONS order"
    for name, value in subs.items():
        _assert_unit_float(value, f"subdimensions.{name}")

    diags = payload["diagnostics"]
    assert isinstance(diags, list)
    for diag in diags:
        assert set(diag) == {"code", "message"}
        assert isinstance(diag["code"], str) and diag["code"]
        assert isinstance(diag["message"], str) and diag["message"]


def _assert_delta_schema(delta: dict) -> None:
    """A ``compare`` delta: meaning_score + the five subdimension deltas (signed floats)."""
    assert set(delta) == {"meaning_score", "subdimensions"}
    assert isinstance(delta["meaning_score"], float)
    assert set(delta["subdimensions"]) == set(_SUBDIMENSIONS)
    for name, value in delta["subdimensions"].items():
        assert isinstance(value, float), f"delta.subdimensions.{name}"


def _assert_slot(slot: dict, *, n: int, is_second: bool) -> None:
    """Validate one ``{"values", "reason"}`` derivative slot."""
    assert set(slot) == {"values", "reason"}
    if is_second and n < 3:
        assert slot["values"] is None
        assert isinstance(slot["reason"], str) and slot["reason"]
    else:
        assert isinstance(slot["values"], list)
        expected_len = n - 2 if is_second else n - 1
        assert len(slot["values"]) == expected_len
        assert slot["reason"] is None
        for value in slot["values"]:
            assert isinstance(value, float)


def _assert_trend_schema(payload: dict, *, n: int) -> None:
    """The documented trend shape for ``n`` measurement points."""
    assert payload["n"] == n
    assert isinstance(payload["paths"], list) and len(payload["paths"]) == n

    assert len(payload["points"]) == n
    for point in payload["points"]:
        assert set(point) == {"meaning_score", "subdimensions"}
        _assert_unit_float(point["meaning_score"], "point.meaning_score")
        assert set(point["subdimensions"]) == set(_SUBDIMENSIONS)

    assert len(payload["per_step_drift"]) == n - 1

    signals = payload["signals"]
    expected_signal_keys = {"meaning_score", *_SUBDIMENSIONS, "drift"}
    assert set(signals) == expected_signal_keys
    for name, signal in signals.items():
        assert set(signal) == {"first", "second"}, name
        _assert_slot(signal["first"], n=n, is_second=False)
        _assert_slot(signal["second"], n=n, is_second=True)

    assert payload["second_difference_available"] is (n >= 3)


# --- score / compare / trend contract shape (engine, offline) ------------


def test_score_schema_from_real_engine() -> None:
    result = score(_FILE_A, embed_fn=synthetic_embed_fn)
    _assert_score_schema(result)
    # Round-trips through JSON unchanged (it is the CLI wire payload).
    assert json.loads(json.dumps(result)) == result


def test_compare_schema_from_real_engine() -> None:
    result = compare(_FILE_A, _FILE_B, embed_fn=synthetic_embed_fn)
    assert set(result) - _ADDITIVE_KEYS == {"before", "after", "delta"}
    _assert_score_schema(result["before"])
    _assert_score_schema(result["after"])
    _assert_delta_schema(result["delta"])


def test_compare_file_against_itself_is_all_zero_delta() -> None:
    result = compare(_FILE_A, _FILE_A, embed_fn=synthetic_embed_fn)
    assert result["delta"]["meaning_score"] == pytest.approx(0.0)
    for value in result["delta"]["subdimensions"].values():
        assert value == pytest.approx(0.0)


def test_trend_schema_n2_second_unavailable_with_reason() -> None:
    result = trend([_FILE_A, _FILE_B], embed_fn=synthetic_embed_fn)
    _assert_trend_schema(result, n=2)
    # At n==2 every second-difference slot is explicitly unavailable-with-reason.
    for name, signal in result["signals"].items():
        assert signal["second"]["values"] is None, name
        assert "at least 3" in signal["second"]["reason"], name


def test_trend_schema_n3_second_populated() -> None:
    result = trend([_FILE_A, _FILE_B, _FILE_C], embed_fn=synthetic_embed_fn)
    _assert_trend_schema(result, n=3)
    for name, signal in result["signals"].items():
        assert signal["second"]["values"] is not None, name
        assert len(signal["second"]["values"]) == 1, name


# --- compare vs trend agreement on a shared two-point series --------------


def test_compare_delta_equals_trend_first_differences() -> None:
    """compare(a, b).delta == trend([a, b]) first differences, same embed_fn.

    Both reduce to score(b) - score(a) for meaning_score and every subdimension
    through the same ``measure`` machinery, so on exactly two points they must
    agree bit-for-bit.
    """
    delta = compare(_FILE_A, _FILE_B, embed_fn=synthetic_embed_fn)["delta"]
    signals = trend([_FILE_A, _FILE_B], embed_fn=synthetic_embed_fn)["signals"]

    # meaning_score: single first difference == the scalar delta.
    assert signals["meaning_score"]["first"]["values"][0] == pytest.approx(delta["meaning_score"])
    # each subdimension: single first difference == that subdimension's delta.
    for sub in _SUBDIMENSIONS:
        assert signals[sub]["first"]["values"][0] == pytest.approx(delta["subdimensions"][sub])


# --- the real CLI wire format equals the contract (offline) ---------------


def _inject(monkeypatch: pytest.MonkeyPatch, name: str, real) -> None:
    """Point a CLI handler's engine symbol at the real engine + synthetic embedder."""
    monkeypatch.setattr(
        f"coherence.cli._commands.meaning.{name}",
        partial(real, embed_fn=synthetic_embed_fn),
    )


def test_cli_score_json_matches_contract(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _inject(monkeypatch, "score", score)
    rc = main(["meaning", "score", str(_FILE_A), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    _assert_score_schema(payload)


def test_cli_compare_json_matches_contract(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _inject(monkeypatch, "compare", compare)
    rc = main(["meaning", "compare", str(_FILE_A), str(_FILE_B), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) - _ADDITIVE_KEYS == {"before", "after", "delta"}
    _assert_score_schema(payload["before"])
    _assert_score_schema(payload["after"])
    _assert_delta_schema(payload["delta"])


def test_cli_trend_json_matches_contract(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _inject(monkeypatch, "trend", trend)
    rc = main(["meaning", "trend", str(_FILE_A), str(_FILE_B), str(_FILE_C), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    _assert_trend_schema(payload, n=3)


def test_registry_and_contract_subdimensions_agree() -> None:
    """The five contract subdimensions are exactly DIMENSIONS minus the global axis."""
    assert tuple(d for d in DIMENSIONS if d != "meaning") == _SUBDIMENSIONS
