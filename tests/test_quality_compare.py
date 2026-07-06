"""Tests for coherence.quality.compare — the two-point quality delta engine.

Every test is fully OFFLINE and deterministic, using the ``no_sockets`` fixture
to verify zero network access. The injected ``assess`` function (via dependency
injection or monkeypatch) can be controlled for deterministic results.

Acceptance criteria (plan task t12):

1. Compare emits before/after envelopes plus a delta map whose keys mirror
   the quality components (freshness, provenance, fidelity and their
   _confidence entries), all signed — assert a case where one component rises
   (positive delta) and another falls (negative delta).
2. Runs fully offline like quality score — reuse the same socket-blocking test
   fixture pattern used in tests/test_quality_score.py.
"""

from __future__ import annotations

import inspect
import socket
from datetime import date

import pytest

from coherence.quality.compare import compare
from coherence.quality.score import score_text

_REF = date(2026, 7, 7)

_GOOD = (
    "As of 2026-07-01, per https://example.com/study, throughput rose 42%. "
    "See also coherence/quality/score.py."
)
_POOR = "The parser module needs refactoring."


@pytest.fixture
def no_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block all socket creation for the duration of a test (no new deps).

    Any attempt to open a network socket raises, so a test wrapped in this
    fixture proves the code path under it touches no network at all.
    """

    def _blocked(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("network access is blocked in this test")

    monkeypatch.setattr(socket, "socket", _blocked)


# --- contract shape -------------------------------------------------------


def test_compare_returns_exact_top_level_keys(tmp_path, no_sockets) -> None:
    """Compare returns exactly {before, after, delta}."""
    before = tmp_path / "before.txt"
    after = tmp_path / "after.txt"
    before.write_text(_POOR, encoding="utf-8")
    after.write_text(_GOOD, encoding="utf-8")

    result = compare(before, after, reference_date=_REF)
    assert set(result) == {"before", "after", "delta"}


def test_before_and_after_are_full_score_envelopes(tmp_path, no_sockets) -> None:
    """before/after are the full score_text envelopes."""
    before = tmp_path / "before.txt"
    after = tmp_path / "after.txt"
    before.write_text(_POOR, encoding="utf-8")
    after.write_text(_GOOD, encoding="utf-8")

    result = compare(before, after, reference_date=_REF)

    # Verify they match score_text output
    expected_before = score_text(_POOR, reference_date=_REF)
    expected_after = score_text(_GOOD, reference_date=_REF)

    assert result["before"] == expected_before
    assert result["after"] == expected_after

    # Verify they have the expected envelope structure
    for block in (result["before"], result["after"]):
        assert set(block) == {"domain", "score_type", "scores", "frame", "diagnostics"}
        assert block["domain"] == "quality"
        assert block["score_type"] == "rule_based_heuristic"


def test_delta_has_all_score_keys(tmp_path, no_sockets) -> None:
    """Delta keys mirror all keys in the scores map."""
    before = tmp_path / "before.txt"
    after = tmp_path / "after.txt"
    before.write_text(_POOR, encoding="utf-8")
    after.write_text(_GOOD, encoding="utf-8")

    result = compare(before, after, reference_date=_REF)

    # Get the score keys from the envelope
    score_keys = set(result["before"]["scores"].keys())
    delta_keys = set(result["delta"].keys())

    assert delta_keys == score_keys
    assert "freshness" in delta_keys
    assert "provenance" in delta_keys
    assert "fidelity" in delta_keys
    assert "freshness_confidence" in delta_keys
    assert "provenance_confidence" in delta_keys
    assert "fidelity_confidence" in delta_keys


def test_delta_values_are_floats(tmp_path, no_sockets) -> None:
    """All delta values are floats."""
    before = tmp_path / "before.txt"
    after = tmp_path / "after.txt"
    before.write_text(_POOR, encoding="utf-8")
    after.write_text(_GOOD, encoding="utf-8")

    result = compare(before, after, reference_date=_REF)

    for key, value in result["delta"].items():
        assert isinstance(value, float), f"delta[{key}] is not a float"


# --- delta arithmetic: after - before ------------------------------------


def test_delta_is_after_minus_before(tmp_path, no_sockets) -> None:
    """Delta = after - before for all components."""
    before = tmp_path / "before.txt"
    after = tmp_path / "after.txt"
    before.write_text(_POOR, encoding="utf-8")
    after.write_text(_GOOD, encoding="utf-8")

    result = compare(before, after, reference_date=_REF)

    before_scores = result["before"]["scores"]
    after_scores = result["after"]["scores"]
    deltas = result["delta"]

    for key in deltas.keys():
        expected_delta = after_scores[key] - before_scores[key]
        assert deltas[key] == pytest.approx(expected_delta)


def test_positive_delta_means_score_improved(tmp_path, no_sockets) -> None:
    """Positive delta means the after artifact scored higher."""
    # "poor" -> "good": most components should improve
    before = tmp_path / "before.txt"
    after = tmp_path / "after.txt"
    before.write_text(_POOR, encoding="utf-8")
    after.write_text(_GOOD, encoding="utf-8")

    result = compare(before, after, reference_date=_REF)

    # The "good" artifact has more quality signals, so deltas should be positive
    # (at least freshness and provenance should improve)
    assert result["delta"]["freshness"] > 0.0
    assert result["delta"]["provenance"] > 0.0


def test_negative_delta_means_score_declined(tmp_path, no_sockets) -> None:
    """Negative delta means the after artifact scored lower."""
    # Swap roles: good -> poor
    before = tmp_path / "before.txt"
    after = tmp_path / "after.txt"
    before.write_text(_GOOD, encoding="utf-8")
    after.write_text(_POOR, encoding="utf-8")

    result = compare(before, after, reference_date=_REF)

    # The "poor" artifact has fewer quality signals, so deltas should be negative
    assert result["delta"]["freshness"] < 0.0
    assert result["delta"]["provenance"] < 0.0


def test_compare_file_against_itself_yields_all_zero_deltas(tmp_path, no_sockets) -> None:
    """Comparing a file against itself gives all-zero deltas."""
    same = tmp_path / "same.txt"
    same.write_text(_GOOD, encoding="utf-8")

    result = compare(same, same, reference_date=_REF)

    # All deltas should be zero (within floating-point epsilon)
    for value in result["delta"].values():
        assert value == pytest.approx(0.0)

    # Before and after blocks should be identical
    assert result["before"] == result["after"]


# --- mixed signs in a single comparison -----------------------------------


def test_case_with_rising_and_falling_components(tmp_path, no_sockets) -> None:
    """Assert a case where one component rises and another falls.

    This tests the requirement: "assert a case where one component rises
    (positive delta) and another falls (negative delta)."
    """
    # Craft text that has good freshness/dating but poor provenance/citation
    before_text = "As of 2026-06-01, the algorithm works."
    # After: loses the date but gains a citation
    after_text = "According to https://example.com/docs, the algorithm works."

    before = tmp_path / "before.txt"
    after = tmp_path / "after.txt"
    before.write_text(before_text, encoding="utf-8")
    after.write_text(after_text, encoding="utf-8")

    result = compare(before, after, reference_date=_REF)

    # Check that we have both positive and negative deltas
    all_deltas = list(result["delta"].values())
    has_positive = any(d > 0.0 for d in all_deltas)
    has_negative = any(d < 0.0 for d in all_deltas)

    assert has_positive, "No positive deltas found"
    assert has_negative, "No negative deltas found"


# --- reference_date parameter threading ---------------------------------


def test_reference_date_is_threaded_to_both_assessments(tmp_path, no_sockets) -> None:
    """reference_date parameter is used for both before and after scoring."""
    before = tmp_path / "before.txt"
    after = tmp_path / "after.txt"
    before.write_text("As of 2026-01-01, this is old.", encoding="utf-8")
    after.write_text("As of 2026-07-01, this is recent.", encoding="utf-8")

    result = compare(before, after, reference_date=_REF)

    # Verify the scores used a consistent reference_date
    # (freshness should differ between old and recent)
    assert result["delta"]["freshness"] > 0.0

    # Should match direct score_text calls with same reference_date
    direct_before = score_text("As of 2026-01-01, this is old.", reference_date=_REF)
    direct_after = score_text("As of 2026-07-01, this is recent.", reference_date=_REF)

    assert result["before"] == direct_before
    assert result["after"] == direct_after


def test_default_reference_date_is_none(tmp_path, no_sockets) -> None:
    """Default reference_date parameter is None."""
    sig = inspect.signature(compare)
    assert sig.parameters["reference_date"].default is None


# --- offline guarantee ---------------------------------------------------


def test_compare_runs_with_sockets_blocked(tmp_path) -> None:
    """Compare runs with zero network access (sockets blocked)."""
    # This test DOES NOT use the no_sockets fixture in the signature
    # but applies it manually, so we can assert the socket blocking worked.
    before = tmp_path / "before.txt"
    after = tmp_path / "after.txt"
    before.write_text(_POOR, encoding="utf-8")
    after.write_text(_GOOD, encoding="utf-8")

    # Block sockets
    original_socket = socket.socket

    def _blocked(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("network access is blocked in this test")

    socket.socket = _blocked
    try:
        # If this succeeds, we verified zero network access
        result = compare(before, after, reference_date=_REF)
        assert result is not None
        assert "delta" in result
    finally:
        socket.socket = original_socket


# --- string path handling ------------------------------------------------


def test_compare_accepts_string_paths(tmp_path, no_sockets) -> None:
    """Compare accepts string paths in addition to Path objects."""
    before = tmp_path / "before.txt"
    after = tmp_path / "after.txt"
    before.write_text(_POOR, encoding="utf-8")
    after.write_text(_GOOD, encoding="utf-8")

    # Pass as strings, not Path objects
    result = compare(str(before), str(after), reference_date=_REF)

    assert set(result) == {"before", "after", "delta"}
    assert "freshness" in result["delta"]
