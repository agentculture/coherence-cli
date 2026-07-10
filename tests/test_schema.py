"""Offline contract tests for ``coherence.schema`` — the shared measurement envelope.

The envelope is the common JSON shape every NEW measurement domain (quality,
signal, investiture, assess) emits from day one, per
``docs/envelope.md``: ``{"domain", "score_type", "scores", "frame",
"diagnostics"}``. These tests cover the ``build_envelope``/``validate_envelope``
pair: a valid envelope round-trips unchanged, every documented field is
type-checked, an explicitly absent ``frame`` (``None`` or a machine-readable
null-frame dict) is accepted, and every rejection raises the dedicated
:class:`~coherence.schema.EnvelopeError` carrying a machine-readable ``code``
rather than a bare ``ValueError``/``KeyError``/``TypeError``.

Fully offline: no network, no filesystem I/O beyond importing the module.
"""

from __future__ import annotations

import json

import pytest

from coherence.schema import EnvelopeError, build_envelope, null_frame, validate_envelope

_ENVELOPE_KEYS = {"domain", "score_type", "scores", "frame", "diagnostics"}


def _full_frame() -> dict:
    return {
        "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
        "embedding_endpoint": "http://localhost:8001/v1",
        "anchor_set": "meaning-v1",
        "projection_method": "contrastive_axis",
    }


# --- build_envelope / validate_envelope round-trip ------------------------


def test_build_envelope_has_exactly_the_five_documented_keys() -> None:
    envelope = build_envelope(
        domain="quality",
        score_type="rule_based_heuristic",
        scores={"freshness": 0.8, "provenance": 0.5},
        frame=None,
        diagnostics=[],
    )
    assert set(envelope) == _ENVELOPE_KEYS


def test_build_envelope_round_trips_through_validate_with_full_frame() -> None:
    envelope = build_envelope(
        domain="meaning",
        score_type="model_relative_anchor_defined_projection",
        scores={"meaning_score": 0.62},
        frame=_full_frame(),
        diagnostics=[{"code": "missing_owner", "message": "no owner named"}],
    )
    assert validate_envelope(envelope) == envelope
    # Round-trips through JSON unchanged (it is a wire payload).
    assert json.loads(json.dumps(envelope)) == envelope


def test_build_envelope_round_trips_with_explicit_null_frame() -> None:
    """An absent frame is representable as ``{"frame": None}`` + a diagnostic."""
    envelope = build_envelope(
        domain="signal",
        score_type="rule_based_heuristic",
        scores={"drift": 0.1},
        frame=None,
        diagnostics=[{"code": "frame_unavailable", "message": "input carried no provenance"}],
    )
    assert envelope["frame"] is None
    assert validate_envelope(envelope) == envelope


def test_build_envelope_accepts_null_frame_helper_dict() -> None:
    """The alternative absent-frame form: a null-frame dict with a machine-readable reason."""
    frame = null_frame("embedding endpoint was down at measurement time")
    envelope = build_envelope(
        domain="investiture",
        score_type="rule_based_heuristic",
        scores={"stake": 0.3},
        frame=frame,
        diagnostics=[],
    )
    assert isinstance(envelope["frame"], dict)
    assert envelope["frame"]["available"] is False
    assert isinstance(envelope["frame"]["reason"], str) and envelope["frame"]["reason"]
    assert validate_envelope(envelope) == envelope


def test_build_envelope_defaults_diagnostics_to_empty_list() -> None:
    envelope = build_envelope(
        domain="quality", score_type="rule_based_heuristic", scores={"x": 1.0}, frame=None
    )
    assert envelope["diagnostics"] == []
    assert validate_envelope(envelope) == envelope


def test_build_envelope_copies_inputs_defensively() -> None:
    """Mutating the caller's dicts after the call must not affect the envelope."""
    scores = {"x": 1.0}
    frame = _full_frame()
    diags = [{"code": "c", "message": "m"}]
    envelope = build_envelope(
        domain="quality",
        score_type="rule_based_heuristic",
        scores=scores,
        frame=frame,
        diagnostics=diags,
    )
    scores["x"] = 999.0
    frame["embedding_model"] = "tampered"
    diags.append({"code": "extra", "message": "extra"})
    assert envelope["scores"]["x"] == 1.0
    assert envelope["frame"]["embedding_model"] == "Qwen/Qwen3-Embedding-0.6B"
    assert len(envelope["diagnostics"]) == 1


# --- rejection: named error with a machine-readable code ------------------


def test_missing_domain_key_rejected_with_envelope_error() -> None:
    bad = {
        "score_type": "rule_based_heuristic",
        "scores": {},
        "frame": None,
        "diagnostics": [],
    }
    with pytest.raises(EnvelopeError) as excinfo:
        validate_envelope(bad)
    assert isinstance(excinfo.value.code, str) and excinfo.value.code


def test_non_dict_scores_rejected_with_envelope_error() -> None:
    bad = {
        "domain": "quality",
        "score_type": "rule_based_heuristic",
        "scores": [1, 2, 3],
        "frame": None,
        "diagnostics": [],
    }
    with pytest.raises(EnvelopeError) as excinfo:
        validate_envelope(bad)
    assert isinstance(excinfo.value.code, str) and excinfo.value.code


def test_missing_frame_key_entirely_is_rejected_not_treated_as_null() -> None:
    """The 'frame' key itself must be present — a missing key differs from an explicit null."""
    bad = {
        "domain": "quality",
        "score_type": "rule_based_heuristic",
        "scores": {},
        "diagnostics": [],
    }
    with pytest.raises(EnvelopeError) as excinfo:
        validate_envelope(bad)
    assert isinstance(excinfo.value.code, str) and excinfo.value.code


def test_missing_diagnostics_key_rejected() -> None:
    bad = {
        "domain": "quality",
        "score_type": "rule_based_heuristic",
        "scores": {},
        "frame": None,
    }
    with pytest.raises(EnvelopeError):
        validate_envelope(bad)


def test_empty_domain_string_rejected() -> None:
    bad = {
        "domain": "",
        "score_type": "rule_based_heuristic",
        "scores": {},
        "frame": None,
        "diagnostics": [],
    }
    with pytest.raises(EnvelopeError):
        validate_envelope(bad)


def test_non_string_domain_rejected() -> None:
    bad = {
        "domain": 123,
        "score_type": "rule_based_heuristic",
        "scores": {},
        "frame": None,
        "diagnostics": [],
    }
    with pytest.raises(EnvelopeError):
        validate_envelope(bad)


def test_missing_score_type_rejected() -> None:
    bad = {
        "domain": "quality",
        "scores": {},
        "frame": None,
        "diagnostics": [],
    }
    with pytest.raises(EnvelopeError):
        validate_envelope(bad)


def test_non_numeric_score_value_rejected() -> None:
    bad = {
        "domain": "quality",
        "score_type": "rule_based_heuristic",
        "scores": {"freshness": "high"},
        "frame": None,
        "diagnostics": [],
    }
    with pytest.raises(EnvelopeError):
        validate_envelope(bad)


def test_frame_of_wrong_type_rejected() -> None:
    bad = {
        "domain": "quality",
        "score_type": "rule_based_heuristic",
        "scores": {},
        "frame": "not-a-dict-or-none",
        "diagnostics": [],
    }
    with pytest.raises(EnvelopeError):
        validate_envelope(bad)


def test_diagnostics_not_a_list_rejected() -> None:
    bad = {
        "domain": "quality",
        "score_type": "rule_based_heuristic",
        "scores": {},
        "frame": None,
        "diagnostics": {"code": "x", "message": "y"},
    }
    with pytest.raises(EnvelopeError):
        validate_envelope(bad)


def test_diagnostic_entry_missing_message_rejected() -> None:
    bad = {
        "domain": "quality",
        "score_type": "rule_based_heuristic",
        "scores": {},
        "frame": None,
        "diagnostics": [{"code": "x"}],
    }
    with pytest.raises(EnvelopeError):
        validate_envelope(bad)


def test_diagnostic_entry_extra_key_rejected() -> None:
    bad = {
        "domain": "quality",
        "score_type": "rule_based_heuristic",
        "scores": {},
        "frame": None,
        "diagnostics": [{"code": "x", "message": "y", "extra": "z"}],
    }
    with pytest.raises(EnvelopeError):
        validate_envelope(bad)


def test_validate_envelope_rejects_non_dict_input() -> None:
    with pytest.raises(EnvelopeError):
        validate_envelope(["not", "a", "dict"])  # type: ignore[arg-type]


def test_error_codes_are_distinguishable_across_failure_kinds() -> None:
    """Different failure kinds should carry different machine-readable codes."""
    missing_domain = {
        "score_type": "rule_based_heuristic",
        "scores": {},
        "frame": None,
        "diagnostics": [],
    }
    bad_scores = {
        "domain": "quality",
        "score_type": "rule_based_heuristic",
        "scores": "nope",
        "frame": None,
        "diagnostics": [],
    }
    with pytest.raises(EnvelopeError) as e1:
        validate_envelope(missing_domain)
    with pytest.raises(EnvelopeError) as e2:
        validate_envelope(bad_scores)
    assert e1.value.code != e2.value.code
