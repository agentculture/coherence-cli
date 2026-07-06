"""Tests for coherence.assess — one verb, every applicable domain (plan task t15).

Every test here is fully OFFLINE: the embedding function is injected as a
synthetic, deterministic ``embed_fn`` (the shared ``tests._meaning_synthetic``
hash-derived embedder, or a raising stub that simulates an unreachable
endpoint), so no real ``/v1/embeddings`` endpoint is ever contacted.

Acceptance criteria under test (plan task t15 / frame claim c18, honesty
condition h14):

1. With the embed endpoint mocked DOWN, ``assess`` returns quality's full
   result plus meaning's offline diagnostics, and lists meaning/investiture as
   unavailable with machine-readable reasons — a normal return (nothing
   raised), never a silently dropped domain.
2. With the endpoint up (synthetic embed_fn), the report contains one entry
   per available domain keyed by domain name — quality, meaning, investiture
   all present in ``domains``, and ``unavailable`` is empty.
"""

from __future__ import annotations

from coherence.assess import DOMAIN, SCORE_TYPE, assess
from coherence.investiture.score import score as investiture_score
from coherence.meaning import EmbedUnavailable
from coherence.meaning.score import offline_result as meaning_offline_result
from coherence.meaning.score import score as meaning_score
from coherence.quality.score import score_text as quality_score_text
from coherence.schema import validate_envelope

from ._meaning_synthetic import synthetic_embed_fn

_RICH_TEXT = (
    "If we ship this unpatched the user table leaks and we breach GDPR, so "
    "@alice (on-call) must run `make rollback` before 09:00 — otherwise the "
    "outage continues.\n- [ ] roll back now\nNext: verify row counts."
)


def _write(tmp_path, text: str = _RICH_TEXT, name: str = "a.md") -> "object":
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _raising_embed(texts: list[str]) -> list[list[float]]:
    """A synthetic ``embed_fn`` that simulates an unreachable endpoint."""
    raise EmbedUnavailable("embedding endpoint unreachable (test stub)")


# --- assess itself satisfies the shared envelope ---------------------------


def test_assess_validates_as_a_shared_envelope(tmp_path) -> None:
    path = _write(tmp_path)
    result = assess(path, embed_fn=synthetic_embed_fn)
    # validate_envelope only checks the five required keys are present and
    # well-formed; it does not reject the extra domains/unavailable/artifact
    # top-level keys (the same technique investiture relies on).
    assert validate_envelope(result) == result


def test_domain_and_score_type_are_the_declared_constants(tmp_path) -> None:
    result = assess(_write(tmp_path), embed_fn=synthetic_embed_fn)
    assert result["domain"] == "assess" == DOMAIN
    assert result["score_type"] == SCORE_TYPE
    assert isinstance(result["score_type"], str) and result["score_type"]


def test_assess_scores_is_empty_and_frame_is_none(tmp_path) -> None:
    # assess computes no numbers of its own; every number lives in `domains`,
    # and there is no single measurement frame spanning multiple domains.
    result = assess(_write(tmp_path), embed_fn=synthetic_embed_fn)
    assert result["scores"] == {}
    assert result["frame"] is None


def test_artifact_names_the_scored_path(tmp_path) -> None:
    path = _write(tmp_path)
    result = assess(path, embed_fn=synthetic_embed_fn)
    assert result["artifact"] == str(path)


def test_accepts_string_paths(tmp_path) -> None:
    path = _write(tmp_path)
    result = assess(str(path), embed_fn=synthetic_embed_fn)
    assert result["artifact"] == str(path)


# --- acceptance criterion 2: endpoint up, every domain present -------------


def test_endpoint_up_every_domain_present_and_unavailable_empty(tmp_path) -> None:
    path = _write(tmp_path)
    result = assess(path, embed_fn=synthetic_embed_fn)

    assert set(result["domains"]) == {"quality", "meaning", "investiture"}
    assert result["unavailable"] == {}
    assert result["diagnostics"] == []


def test_quality_domain_matches_the_quality_engine_directly(tmp_path) -> None:
    path = _write(tmp_path)
    result = assess(path, embed_fn=synthetic_embed_fn)
    expected_quality = quality_score_text(_RICH_TEXT)
    assert result["domains"]["quality"] == expected_quality


def test_meaning_domain_matches_the_meaning_engine_directly(tmp_path) -> None:
    path = _write(tmp_path)
    result = assess(path, embed_fn=synthetic_embed_fn)
    expected_meaning = meaning_score(path, embed_fn=synthetic_embed_fn)
    assert result["domains"]["meaning"] == expected_meaning
    # meaning keeps its own pinned two-speed shape inside `domains`, not the
    # generic scores-map envelope quality/investiture use.
    assert "meaning_score" in result["domains"]["meaning"]
    assert "subdimensions" in result["domains"]["meaning"]


def test_investiture_domain_matches_the_investiture_engine_directly(tmp_path) -> None:
    path = _write(tmp_path)
    result = assess(path, embed_fn=synthetic_embed_fn)
    expected_investiture = investiture_score(path, embed_fn=synthetic_embed_fn)
    assert result["domains"]["investiture"] == expected_investiture
    assert validate_envelope(result["domains"]["investiture"]) == result["domains"]["investiture"]


def test_quality_envelope_validates_on_its_own(tmp_path) -> None:
    path = _write(tmp_path)
    result = assess(path, embed_fn=synthetic_embed_fn)
    assert validate_envelope(result["domains"]["quality"]) == result["domains"]["quality"]


# --- acceptance criterion 1: endpoint down, partial availability -----------


def test_endpoint_down_returns_normally_never_raises(tmp_path) -> None:
    # The core honesty condition (h14): partial availability is a normal
    # return, not an error.
    result = assess(_write(tmp_path), embed_fn=_raising_embed)
    assert isinstance(result, dict)


def test_endpoint_down_quality_still_present(tmp_path) -> None:
    path = _write(tmp_path)
    result = assess(path, embed_fn=_raising_embed)
    expected_quality = quality_score_text(_RICH_TEXT)
    assert result["domains"]["quality"] == expected_quality


def test_endpoint_down_meaning_and_investiture_absent_from_domains(tmp_path) -> None:
    result = assess(_write(tmp_path), embed_fn=_raising_embed)
    assert set(result["domains"]) == {"quality"}
    assert "meaning" not in result["domains"]
    assert "investiture" not in result["domains"]


def test_endpoint_down_meaning_and_investiture_listed_unavailable_with_reasons(tmp_path) -> None:
    result = assess(_write(tmp_path), embed_fn=_raising_embed)
    assert set(result["unavailable"]) == {"meaning", "investiture"}
    for name in ("meaning", "investiture"):
        entry = result["unavailable"][name]
        assert isinstance(entry["code"], str) and entry["code"]
        assert isinstance(entry["reason"], str) and entry["reason"]
    assert result["unavailable"]["meaning"]["code"] == "embed_endpoint_unreachable"


def test_endpoint_down_offline_meaning_diagnostics_are_surfaced(tmp_path) -> None:
    path = _write(tmp_path)
    result = assess(path, embed_fn=_raising_embed)
    expected_offline = meaning_offline_result(path)
    assert (
        result["unavailable"]["meaning"]["offline_diagnostics"] == expected_offline["diagnostics"]
    )
    # Meaning's offline diagnostics are a real, non-trivial rule-based check —
    # sanity-check they are the well-formed {"code", "message"} shape.
    for diag in result["unavailable"]["meaning"]["offline_diagnostics"]:
        assert set(diag) == {"code", "message"}


def test_endpoint_down_top_level_diagnostics_name_each_unavailable_domain(tmp_path) -> None:
    result = assess(_write(tmp_path), embed_fn=_raising_embed)
    codes = [d["code"] for d in result["diagnostics"]]
    assert codes.count("domain_unavailable") == 2
    messages = " ".join(d["message"] for d in result["diagnostics"])
    assert "meaning" in messages
    assert "investiture" in messages
    for diag in result["diagnostics"]:
        assert set(diag) == {"code", "message"}


def test_endpoint_down_investiture_reason_names_its_dependency_on_meaning(tmp_path) -> None:
    result = assess(_write(tmp_path), embed_fn=_raising_embed)
    assert "meaning" in result["unavailable"]["investiture"]["reason"]


def test_endpoint_down_investiture_not_double_attempted(monkeypatch, tmp_path) -> None:
    # investiture derives entirely from meaning; once meaning has failed,
    # assess should not make a second (equally doomed) embed attempt through
    # investiture.score — sanity-checked by counting calls to the failing fn.
    calls = {"n": 0}

    def _counting_raising_embed(texts: list[str]) -> list[list[float]]:
        calls["n"] += 1
        raise EmbedUnavailable("embedding endpoint unreachable (test stub)")

    assess(_write(tmp_path), embed_fn=_counting_raising_embed)
    assert calls["n"] == 1


# --- diagnostics list shape convention (repo-wide {"code", "message"}) -----


def test_diagnostics_entries_are_well_formed_when_available(tmp_path) -> None:
    result = assess(_write(tmp_path), embed_fn=synthetic_embed_fn)
    for diag in result["diagnostics"]:
        assert set(diag) == {"code", "message"}
        assert isinstance(diag["code"], str) and diag["code"]
        assert isinstance(diag["message"], str) and diag["message"]
