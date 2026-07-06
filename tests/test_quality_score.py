"""Tests for coherence.quality.score — the offline quality score engine.

Every test is fully OFFLINE and deterministic. Acceptance criteria (plan
task t11):

1. Quality score runs with ZERO network access — the ``no_sockets`` fixture
   monkeypatches ``socket.socket`` to raise (no new dependencies), and scoring
   still produces the shared envelope with ``domain == "quality"``.
2. Diagnostics NAME what the heuristics could NOT verify (source liveness,
   actual publication date) — asserted present on an artifact WITH citations.
3. An artifact with no dateable statements gets LOWERED confidence with a
   diagnostic (``no_dateable_statements``), never a fabricated freshness score.
"""

from __future__ import annotations

import inspect
import json
import socket
from datetime import date

import pytest

from coherence.quality.score import assess, score_text
from coherence.schema import validate_envelope

_REF = date(2026, 7, 7)

_CITED = (
    "According to the benchmark at https://example.com/report, throughput rose. "
    "See also coherence/quality/score.py."
)
_UNDATED = "The parser module should be split into three smaller files for clarity."
_DATED_RICH = (
    'As of 2026-07-01, per https://example.com/study, the RFC states "retries '
    'MUST back off"; latency fell 42% to 118ms.'
)


@pytest.fixture
def no_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block all socket creation for the duration of a test (no new deps).

    Any attempt to open a network socket raises, so a test wrapped in this
    fixture proves the code path under it touches no network at all.
    """

    def _blocked(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("network access is blocked in this test")

    monkeypatch.setattr(socket, "socket", _blocked)


def _codes(envelope: dict) -> list[str]:
    return [entry["code"] for entry in envelope["diagnostics"]]


# --- acceptance #1: zero-network + shared envelope ------------------------


def test_score_text_runs_with_sockets_blocked(no_sockets: None) -> None:
    envelope = score_text(_DATED_RICH, reference_date=_REF)
    assert envelope["domain"] == "quality"
    assert envelope["score_type"] == "rule_based_heuristic"


def test_score_text_emits_a_valid_shared_envelope() -> None:
    envelope = score_text(_DATED_RICH, reference_date=_REF)
    # Round-trips through the shared contract validator unchanged.
    assert validate_envelope(envelope) == envelope
    assert set(envelope) == {"domain", "score_type", "scores", "frame", "diagnostics"}


def test_frame_is_an_explicit_null_frame_never_fabricated() -> None:
    frame = score_text(_DATED_RICH, reference_date=_REF)["frame"]
    # Quality is rule-based: the frame must be an explicit null-frame dict
    # carrying a machine-readable reason, never a made-up embedding frame.
    assert frame is not None
    assert frame["available"] is False
    assert frame["code"] == "rule_based_no_embedding_frame"


def test_scores_carry_three_components_plus_visible_confidences() -> None:
    scores = score_text(_DATED_RICH, reference_date=_REF)["scores"]
    for component in ("freshness", "provenance", "fidelity"):
        assert component in scores
        assert component + "_confidence" in scores
    # Every score is a float in the unit range.
    for name, value in scores.items():
        assert isinstance(value, float), name
        assert 0.0 <= value <= 1.0, name


def test_score_text_output_is_json_serializable_round_trip() -> None:
    envelope = score_text(_DATED_RICH, reference_date=_REF)
    assert json.loads(json.dumps(envelope)) == envelope


# --- acceptance #2: name what cannot be verified --------------------------


def test_cited_artifact_names_unverifiable_liveness_and_publication_date() -> None:
    codes = _codes(score_text(_CITED, reference_date=_REF))
    assert "source_liveness_unverified" in codes
    assert "publication_date_unverified" in codes


def test_diagnostics_are_wellformed_code_message_dicts() -> None:
    for entry in score_text(_CITED, reference_date=_REF)["diagnostics"]:
        assert set(entry) == {"code", "message"}
        assert isinstance(entry["code"], str) and entry["code"]
        assert isinstance(entry["message"], str) and entry["message"]


def test_diagnostics_are_deduplicated() -> None:
    # publication_date_unverified can be implied by both a date and a source;
    # it must appear at most once.
    codes = _codes(score_text(_DATED_RICH, reference_date=_REF))
    assert len(codes) == len(set(codes))


# --- acceptance #3: no dateable statements => lowered confidence ----------


def test_no_dateable_statements_flags_diagnostic() -> None:
    assert "no_dateable_statements" in _codes(score_text(_UNDATED, reference_date=_REF))


def test_no_dateable_statements_never_fabricates_freshness() -> None:
    scores = score_text(_UNDATED, reference_date=_REF)["scores"]
    # Freshness reflects ABSENCE of evidence (0.0), not an invented number...
    assert abs(scores["freshness"]) <= 1e-9
    # ...and its confidence is explicitly lowered.
    assert scores["freshness_confidence"] < 0.5


def test_undated_confidence_is_lower_than_dated_confidence() -> None:
    undated = score_text(_UNDATED, reference_date=_REF)["scores"]["freshness_confidence"]
    dated = score_text("As of 2026-07-01 rebuilt.", reference_date=_REF)["scores"][
        "freshness_confidence"
    ]
    assert undated < dated


# --- composability for t12 (quality compare) ------------------------------


def test_assess_exposes_raw_components_confidence_and_diagnostics() -> None:
    result = assess(_DATED_RICH, reference_date=_REF)
    assert set(result) == {"components", "confidence", "diagnostics"}
    assert set(result["components"]) == {"freshness", "provenance", "fidelity"}
    assert set(result["confidence"]) == {"freshness", "provenance", "fidelity"}
    assert isinstance(result["diagnostics"], list)


def test_score_text_reference_date_defaults_to_none() -> None:
    # The library default is None (no now() in library paths); the CLI boundary
    # supplies today. A date present but no reference => age not derivable.
    sig = inspect.signature(score_text)
    assert sig.parameters["reference_date"].default is None
    codes = _codes(score_text("Dated 2026-01-15 here.", reference_date=None))
    assert "age_not_derivable" in codes


def test_scoring_is_deterministic_across_calls() -> None:
    first = score_text(_DATED_RICH, reference_date=_REF)
    second = score_text(_DATED_RICH, reference_date=_REF)
    assert first == second
