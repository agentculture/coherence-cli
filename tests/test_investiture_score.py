"""Tests for coherence.investiture.score — estimated micro-investiture.

Every test here is fully OFFLINE: the embedding function is injected as a
synthetic, deterministic ``embed_fn`` (the shared ``tests._meaning_synthetic``
hash-derived embedder, or a raising stub), so no real ``/v1/embeddings``
endpoint is ever contacted. Acceptance criteria under test (plan task t13):

1. ``score(path)`` carries ``investiture_score``, ``mode == "estimated"``,
   ``components`` (four numeric values plus ``persistence_signal`` /
   ``integration_signal`` / ``behavioral_effect`` explicitly ``None``),
   ``evidence`` flags, and the ``missing_behavioral_outcome`` diagnostic — AND
   a full shared measurement envelope (``domain``, ``score_type``, ``scores``,
   ``frame``, ``diagnostics``) that validates via
   :func:`coherence.schema.validate_envelope`.
2. With the embed endpoint unreachable, ``score`` raises the SAME
   :class:`~coherence.meaning.EmbedUnavailable` class the meaning engine
   raises (not a duplicate exception type) — proving investiture calls into
   :mod:`coherence.meaning` rather than reimplementing embedding/axis logic.
3. ``frame`` is the meaning result's frame block, passed through verbatim.

No mystical language is asserted absent from the output (no "soul", "spirit",
etc.) — investiture is described as an estimated causal-imprint measurement,
never a literal soul.
"""

from __future__ import annotations

import inspect
import json

import pytest

from coherence.investiture.score import DOMAIN, MODE_ESTIMATED, SCORE_TYPE, score
from coherence.meaning import EmbedUnavailable
from coherence.meaning import EmbedUnavailable as EmbedUnavailableFromMeaningPackage
from coherence.meaning.embed import EmbedUnavailable as EmbedUnavailableFromEmbedModule
from coherence.meaning.embed import embed_texts
from coherence.meaning.score import score as meaning_score
from coherence.schema import validate_envelope

from ._meaning_synthetic import synthetic_embed_fn

_NUMERIC_COMPONENTS = ("meaning_density", "agency_coupling", "future_constraint", "affordance")
_NULL_COMPONENTS = ("persistence_signal", "integration_signal", "behavioral_effect")

_RICH_TEXT = (
    "If we ship this unpatched the user table leaks and we breach GDPR, so "
    "@alice (on-call) must run `make rollback` before 09:00 — otherwise the "
    "outage continues.\n- [ ] roll back now\nNext: verify row counts."
)
_VAGUE_TEXT = "Something happened yesterday."


def _write(tmp_path, name: str, text: str) -> "object":
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _raising_embed(texts: list[str]) -> list[list[float]]:
    """A synthetic ``embed_fn`` that simulates an unreachable endpoint."""
    raise EmbedUnavailable("embedding endpoint unreachable (test stub)")


# --- the dual output contract: shared envelope + issue-#8 fields ----------


def test_score_carries_both_the_envelope_and_issue8_fields(tmp_path) -> None:
    result = score(_write(tmp_path, "a.md", _RICH_TEXT), embed_fn=synthetic_embed_fn)
    envelope_keys = {"domain", "score_type", "scores", "frame", "diagnostics"}
    issue8_keys = {"investiture_score", "mode", "components", "evidence"}
    assert envelope_keys <= set(result)
    assert issue8_keys <= set(result)
    # No stray keys beyond the union of both contracts.
    assert set(result) == envelope_keys | issue8_keys


def test_score_validates_as_a_shared_envelope(tmp_path) -> None:
    result = score(_write(tmp_path, "a.md", _RICH_TEXT), embed_fn=synthetic_embed_fn)
    # validate_envelope only checks the five required keys are present and
    # well-formed; it does not reject the extra issue-#8 top-level keys.
    assert validate_envelope(result) == result


def test_domain_and_score_type_are_the_declared_constants(tmp_path) -> None:
    result = score(_write(tmp_path, "a.md", _RICH_TEXT), embed_fn=synthetic_embed_fn)
    assert result["domain"] == "investiture" == DOMAIN
    assert result["score_type"] == "estimated_micro_investiture" == SCORE_TYPE


def test_mode_is_estimated(tmp_path) -> None:
    result = score(_write(tmp_path, "a.md", _RICH_TEXT), embed_fn=synthetic_embed_fn)
    assert result["mode"] == "estimated" == MODE_ESTIMATED


def test_components_has_four_numeric_and_three_explicit_nulls(tmp_path) -> None:
    result = score(_write(tmp_path, "a.md", _RICH_TEXT), embed_fn=synthetic_embed_fn)
    components = result["components"]
    assert set(components) == set(_NUMERIC_COMPONENTS) | set(_NULL_COMPONENTS)
    for name in _NUMERIC_COMPONENTS:
        assert isinstance(components[name], float), name
        assert 0.0 <= components[name] <= 1.0, name
    for name in _NULL_COMPONENTS:
        assert components[name] is None, name


def test_scores_map_carries_only_the_numeric_values(tmp_path) -> None:
    result = score(_write(tmp_path, "a.md", _RICH_TEXT), embed_fn=synthetic_embed_fn)
    scores = result["scores"]
    # scores is the envelope's numeric-only map: investiture_score plus the
    # four numeric components — the null triplet lives only in `components`,
    # never in `scores` (validate_envelope requires every scores value to be
    # numeric, so a None there would fail validation).
    assert set(scores) == {"investiture_score"} | set(_NUMERIC_COMPONENTS)
    for name, value in scores.items():
        assert isinstance(value, float), name
        assert 0.0 <= value <= 1.0, name


def test_evidence_flags_artifact_only(tmp_path) -> None:
    result = score(_write(tmp_path, "a.md", _RICH_TEXT), embed_fn=synthetic_embed_fn)
    assert result["evidence"] == {
        "source": "artifact_only",
        "has_history": False,
        "has_outcome_labels": False,
    }


def test_missing_behavioral_outcome_diagnostic_present(tmp_path) -> None:
    result = score(_write(tmp_path, "a.md", _RICH_TEXT), embed_fn=synthetic_embed_fn)
    codes = [d["code"] for d in result["diagnostics"]]
    assert "missing_behavioral_outcome" in codes
    diag = next(d for d in result["diagnostics"] if d["code"] == "missing_behavioral_outcome")
    assert diag["message"] == (
        "Investiture is estimated from artifact structure only; no downstream "
        "behavior was measured."
    )


def test_diagnostics_pass_through_meanings_own_diagnostics(tmp_path) -> None:
    path = _write(tmp_path, "a.md", _VAGUE_TEXT)
    result = score(path, embed_fn=synthetic_embed_fn)
    meaning_result = meaning_score(path, embed_fn=synthetic_embed_fn)

    # Every diagnostic meaning raised is passed through unchanged...
    for diag in meaning_result["diagnostics"]:
        assert diag in result["diagnostics"]
    # ...and the investiture-specific diagnostic is appended after them.
    codes = [d["code"] for d in result["diagnostics"]]
    assert codes[-1] == "missing_behavioral_outcome"
    assert len(codes) == len(meaning_result["diagnostics"]) + 1


def test_healthy_artifact_still_carries_missing_behavioral_outcome(tmp_path) -> None:
    # Even when meaning itself has no diagnostics to flag, investiture's own
    # "not measured" diagnostic still fires — it is not conditional on meaning.
    result = score(_write(tmp_path, "a.md", _RICH_TEXT), embed_fn=synthetic_embed_fn)
    assert [d["code"] for d in result["diagnostics"]] == ["missing_behavioral_outcome"]


# --- formula: meaning_score * agency * future_constraint * affordance -----


def test_investiture_score_matches_the_documented_formula(tmp_path) -> None:
    path = _write(tmp_path, "a.md", "Deploy the fix so revenue is safe; @bob owns the rollout.")
    result = score(path, embed_fn=synthetic_embed_fn)
    meaning_result = meaning_score(path, embed_fn=synthetic_embed_fn)

    expected = (
        meaning_result["meaning_score"]
        * meaning_result["subdimensions"]["agency"]
        * meaning_result["subdimensions"]["future_constraint"]
        * meaning_result["subdimensions"]["affordance"]
    )
    assert result["investiture_score"] == pytest.approx(expected)
    assert result["scores"]["investiture_score"] == pytest.approx(expected)


def test_components_map_to_the_matching_meaning_subdimensions(tmp_path) -> None:
    path = _write(tmp_path, "a.md", "Deploy the fix so revenue is safe; @bob owns the rollout.")
    result = score(path, embed_fn=synthetic_embed_fn)
    meaning_result = meaning_score(path, embed_fn=synthetic_embed_fn)
    components = result["components"]

    assert components["meaning_density"] == pytest.approx(meaning_result["meaning_score"])
    assert components["agency_coupling"] == pytest.approx(meaning_result["subdimensions"]["agency"])
    assert components["future_constraint"] == pytest.approx(
        meaning_result["subdimensions"]["future_constraint"]
    )
    assert components["affordance"] == pytest.approx(meaning_result["subdimensions"]["affordance"])


def test_investiture_score_is_in_the_unit_range(tmp_path) -> None:
    result = score(_write(tmp_path, "a.md", _RICH_TEXT), embed_fn=synthetic_embed_fn)
    assert 0.0 <= result["investiture_score"] <= 1.0


# --- frame pass-through ----------------------------------------------------


def test_frame_passed_through_verbatim_from_meaning(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COHERENCE_EMBED_URL", "http://invest.test:1234/v1")
    monkeypatch.setenv("COHERENCE_EMBED_MODEL", "invest/test-model")
    path = _write(tmp_path, "a.md", _RICH_TEXT)

    result = score(path, embed_fn=synthetic_embed_fn)
    meaning_result = meaning_score(path, embed_fn=synthetic_embed_fn)

    assert result["frame"] == meaning_result["frame"]
    assert result["frame"]["embedding_endpoint"] == "http://invest.test:1234/v1"
    assert result["frame"]["embedding_model"] == "invest/test-model"


# --- reuse, not duplication: the shared EmbedUnavailable propagates -------


def test_embed_unavailable_is_the_shared_class_not_a_duplicate() -> None:
    # coherence.meaning.embed imports EmbedUnavailable from coherence.meaning
    # rather than defining its own — pin that it is literally the same class
    # object, so a future refactor cannot silently fork it into two types.
    assert EmbedUnavailableFromEmbedModule is EmbedUnavailableFromMeaningPackage


def test_score_propagates_embed_unavailable_when_endpoint_down(tmp_path) -> None:
    path = _write(tmp_path, "a.md", _RICH_TEXT)
    with pytest.raises(EmbedUnavailableFromEmbedModule):
        score(path, embed_fn=_raising_embed)


def test_score_missing_file_raises_file_not_found(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        score(tmp_path / "does-not-exist.md", embed_fn=synthetic_embed_fn)


def test_score_accepts_string_paths(tmp_path) -> None:
    path = _write(tmp_path, "a.md", _RICH_TEXT)
    result = score(str(path), embed_fn=synthetic_embed_fn)
    assert isinstance(result["investiture_score"], float)


def test_default_embed_fn_is_the_real_embed_texts() -> None:
    sig = inspect.signature(score)
    assert sig.parameters["embed_fn"].default is embed_texts


def test_score_output_is_json_serializable_round_trip(tmp_path) -> None:
    result = score(_write(tmp_path, "a.md", _RICH_TEXT), embed_fn=synthetic_embed_fn)
    assert json.loads(json.dumps(result)) == result


# --- no mystical language ---------------------------------------------------


def test_no_mystical_language_in_output(tmp_path) -> None:
    result = score(_write(tmp_path, "a.md", _RICH_TEXT), embed_fn=synthetic_embed_fn)
    blob = json.dumps(result).lower()
    for banned in ("soul", "spirit", "mystical", "sacred", "divine", "metaphysic"):
        assert banned not in blob
