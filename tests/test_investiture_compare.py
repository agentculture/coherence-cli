"""Tests for coherence.investiture.compare — two-point investiture delta engine.

Every test here is fully OFFLINE, using the shared ``tests._meaning_synthetic``
hash-derived embedder (or a raising stub), so no real ``/v1/embeddings``
endpoint is ever contacted. Acceptance criteria under test (plan task t13):

* ``compare(before, after)`` returns exactly ``{before, after, delta}``, where
  ``before``/``after`` are the full :func:`coherence.investiture.score.score`
  results (each independently validating as a shared measurement envelope, and
  each carrying the meaning frame verbatim).
* ``delta`` carries a signed ``investiture_score`` plus a ``components`` map of
  signed deltas for the four NUMERIC components (the null triplet — being
  unmeasured, not merely zero — has no delta to report).
* Comparing a file against itself yields all-zero deltas; the sign of
  ``delta`` always means ``after - before``.
* The same embed_fn is threaded to both files, and the shared
  ``EmbedUnavailable`` propagates when the endpoint is down (reuse, not
  duplication of the meaning engine's embed path).
"""

from __future__ import annotations

import inspect
import json

import pytest

from coherence.investiture.compare import compare
from coherence.investiture.score import score
from coherence.meaning import EmbedUnavailable
from coherence.meaning.embed import embed_texts
from coherence.schema import validate_envelope

from ._meaning_synthetic import synthetic_embed_fn

_NUMERIC_COMPONENTS = ("meaning_density", "agency_coupling", "future_constraint", "affordance")

_BEFORE_TEXT = "An early, thin note with nothing much in it."
_AFTER_TEXT = (
    "If we ship this unpatched we breach GDPR, so @alice must roll back "
    "before 09:00 or the outage continues. Next: verify row counts."
)


def _write(tmp_path, name: str, text: str) -> "object":
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _raising_embed(texts: list[str]) -> list[list[float]]:
    """A synthetic ``embed_fn`` that simulates an unreachable endpoint."""
    raise EmbedUnavailable("embedding endpoint unreachable (test stub)")


# --- contract shape ---------------------------------------------------------


def test_compare_returns_exact_top_level_keys(tmp_path) -> None:
    before = _write(tmp_path, "before.md", _BEFORE_TEXT)
    after = _write(tmp_path, "after.md", _AFTER_TEXT)
    result = compare(before, after, embed_fn=synthetic_embed_fn)
    assert set(result) == {"before", "after", "delta"}


def test_before_and_after_are_the_full_score_results(tmp_path) -> None:
    before = _write(tmp_path, "before.md", _BEFORE_TEXT)
    after = _write(tmp_path, "after.md", _AFTER_TEXT)
    result = compare(before, after, embed_fn=synthetic_embed_fn)
    assert result["before"] == score(before, embed_fn=synthetic_embed_fn)
    assert result["after"] == score(after, embed_fn=synthetic_embed_fn)


def test_before_and_after_each_validate_as_shared_envelopes(tmp_path) -> None:
    before = _write(tmp_path, "before.md", _BEFORE_TEXT)
    after = _write(tmp_path, "after.md", _AFTER_TEXT)
    result = compare(before, after, embed_fn=synthetic_embed_fn)
    assert validate_envelope(result["before"]) == result["before"]
    assert validate_envelope(result["after"]) == result["after"]


def test_delta_has_investiture_score_and_component_deltas(tmp_path) -> None:
    before = _write(tmp_path, "before.md", _BEFORE_TEXT)
    after = _write(tmp_path, "after.md", _AFTER_TEXT)
    result = compare(before, after, embed_fn=synthetic_embed_fn)
    assert set(result["delta"]) == {"investiture_score", "components"}
    assert isinstance(result["delta"]["investiture_score"], float)
    assert set(result["delta"]["components"]) == set(_NUMERIC_COMPONENTS)
    for name, value in result["delta"]["components"].items():
        assert isinstance(value, float), name


# --- delta arithmetic: after - before ---------------------------------------


def test_delta_is_after_minus_before(tmp_path) -> None:
    before = _write(tmp_path, "before.md", _BEFORE_TEXT)
    after = _write(tmp_path, "after.md", _AFTER_TEXT)
    result = compare(before, after, embed_fn=synthetic_embed_fn)

    before_score = result["before"]
    after_score = result["after"]
    assert result["delta"]["investiture_score"] == pytest.approx(
        after_score["investiture_score"] - before_score["investiture_score"]
    )
    for name in _NUMERIC_COMPONENTS:
        expected = after_score["components"][name] - before_score["components"][name]
        assert result["delta"]["components"][name] == pytest.approx(expected)


def test_compare_file_against_itself_yields_all_zero_deltas(tmp_path) -> None:
    same = _write(tmp_path, "same.md", "Ship the fix so revenue is safe; @bob owns it.")
    result = compare(same, same, embed_fn=synthetic_embed_fn)
    assert result["delta"]["investiture_score"] == pytest.approx(0.0)
    for value in result["delta"]["components"].values():
        assert value == pytest.approx(0.0)
    assert result["before"] == result["after"]


def test_swapping_before_and_after_flips_the_delta_sign(tmp_path) -> None:
    before = _write(tmp_path, "before.md", _BEFORE_TEXT)
    after = _write(tmp_path, "after.md", _AFTER_TEXT)

    forward = compare(before, after, embed_fn=synthetic_embed_fn)
    backward = compare(after, before, embed_fn=synthetic_embed_fn)

    assert backward["delta"]["investiture_score"] == pytest.approx(
        -forward["delta"]["investiture_score"]
    )
    for name in _NUMERIC_COMPONENTS:
        assert backward["delta"]["components"][name] == pytest.approx(
            -forward["delta"]["components"][name]
        )


# --- frame pass-through on both sides ---------------------------------------


def test_frame_passed_through_on_both_sides(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COHERENCE_EMBED_URL", "http://cmp.test:1/v1")
    monkeypatch.setenv("COHERENCE_EMBED_MODEL", "cmp/model")
    before = _write(tmp_path, "before.md", _BEFORE_TEXT)
    after = _write(tmp_path, "after.md", _AFTER_TEXT)
    result = compare(before, after, embed_fn=synthetic_embed_fn)
    assert result["before"]["frame"]["embedding_endpoint"] == "http://cmp.test:1/v1"
    assert result["after"]["frame"]["embedding_endpoint"] == "http://cmp.test:1/v1"
    assert result["before"]["frame"] == result["after"]["frame"]


# --- embed_fn threading + reuse ---------------------------------------------


def test_embed_fn_is_threaded_to_both_files(tmp_path) -> None:
    calls: list[list[str]] = []

    def counting_embed(texts: list[str]) -> list[list[float]]:
        calls.append(list(texts))
        return synthetic_embed_fn(texts)

    before = _write(tmp_path, "before.md", "BEFORE-MARKER text.")
    after = _write(tmp_path, "after.md", "AFTER-MARKER text.")
    compare(before, after, embed_fn=counting_embed)

    # score() embeds once per file, so compare embeds exactly twice.
    assert len(calls) == 2


def test_compare_propagates_embed_unavailable_when_endpoint_down(tmp_path) -> None:
    before = _write(tmp_path, "before.md", _BEFORE_TEXT)
    after = _write(tmp_path, "after.md", _AFTER_TEXT)
    with pytest.raises(EmbedUnavailable):
        compare(before, after, embed_fn=_raising_embed)


def test_default_embed_fn_is_the_real_embed_texts() -> None:
    assert inspect.signature(compare).parameters["embed_fn"].default is embed_texts


def test_compare_output_is_json_serializable_round_trip(tmp_path) -> None:
    before = _write(tmp_path, "before.md", _BEFORE_TEXT)
    after = _write(tmp_path, "after.md", _AFTER_TEXT)
    result = compare(before, after, embed_fn=synthetic_embed_fn)
    assert json.loads(json.dumps(result)) == result


def test_compare_accepts_string_paths(tmp_path) -> None:
    before = _write(tmp_path, "before.md", _BEFORE_TEXT)
    after = _write(tmp_path, "after.md", _AFTER_TEXT)
    result = compare(str(before), str(after), embed_fn=synthetic_embed_fn)
    assert set(result) == {"before", "after", "delta"}
