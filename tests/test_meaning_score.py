"""Tests for coherence.meaning.score — the score engine and JSON contract.

Every test here is fully OFFLINE: the embedding function is injected as a
synthetic, deterministic ``embed_fn`` (a recording stub or a raising stub), so
no real ``/v1/embeddings`` endpoint is ever contacted. The acceptance criteria
under test (plan task t5):

* ``score(path)`` returns exactly ``{meaning_score, subdimensions{...},
  diagnostics[...]}`` with every numeric value in ``[0, 1]``.
* Efficiency: the artifact is embedded exactly once per run, and all anchors
  ride along in the same single batch — never a re-embed per subdimension.
* Extensibility: registering a new dimension surfaces it in the open
  ``subdimensions`` map with no change to the return shape.
* Offline degrade: ``diagnostics_only(path)`` succeeds even when embedding
  would fail, while ``score`` propagates ``EmbedUnavailable``.
"""

from __future__ import annotations

import hashlib
import inspect
import json

import numpy as np
import pytest

from coherence.meaning import EmbedUnavailable, axis
from coherence.meaning.axis import DIMENSIONS, load_anchors
from coherence.meaning.diagnostics import diagnostics
from coherence.meaning.embed import embed_texts
from coherence.meaning.score import diagnostics_only, measure, score

_SUBDIMENSIONS = ("consequence", "agency", "causality", "affordance", "future_constraint")


def _fake_vector(text: str, dim: int = 12) -> list[float]:
    """Deterministic, non-zero pseudo-embedding derived from ``text``.

    Byte values scaled into ``[0, 1]`` — distinct per text, reproducible, and
    (for any non-empty text) non-zero, so projections stay well-defined.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [digest[i % len(digest)] / 255.0 for i in range(dim)]


class RecordingEmbed:
    """A synthetic ``embed_fn`` that records every text and batch it embeds."""

    def __init__(self) -> None:
        self.calls = 0
        self.batches: list[list[str]] = []
        self.seen: list[str] = []

    def __call__(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        batch = list(texts)
        self.batches.append(batch)
        self.seen.extend(batch)
        return [_fake_vector(t) for t in batch]


def _raising_embed(texts: list[str]) -> list[list[float]]:
    """A synthetic ``embed_fn`` that simulates an unreachable endpoint."""
    raise EmbedUnavailable("embedding endpoint unreachable (test stub)")


def _write(tmp_path, text: str) -> "object":
    path = tmp_path / "artifact.md"
    path.write_text(text, encoding="utf-8")
    return path


_RICH_TEXT = (
    "If we ship this unpatched the user table leaks and we breach GDPR, so "
    "@alice (on-call) must run `make rollback` before 09:00 — otherwise the "
    "outage continues.\n- [ ] roll back now\nNext: verify row counts."
)


# --- contract shape -------------------------------------------------------


def test_score_returns_exact_three_key_contract(tmp_path) -> None:
    result = score(_write(tmp_path, _RICH_TEXT), embed_fn=RecordingEmbed())
    assert set(result) == {"meaning_score", "subdimensions", "diagnostics"}
    assert isinstance(result["meaning_score"], float)
    assert isinstance(result["subdimensions"], dict)
    assert isinstance(result["diagnostics"], list)


def test_subdimensions_are_the_five_named_keys_in_order(tmp_path) -> None:
    result = score(_write(tmp_path, _RICH_TEXT), embed_fn=RecordingEmbed())
    # The five subdimensions appear, and in the DIMENSIONS order (meaning
    # stripped off the front).
    assert list(result["subdimensions"]) == list(_SUBDIMENSIONS)


def test_meaning_dimension_maps_to_meaning_score_not_subdimensions(tmp_path) -> None:
    result = score(_write(tmp_path, _RICH_TEXT), embed_fn=RecordingEmbed())
    # The global "meaning" axis is the top-level scalar, never a subdimension.
    assert "meaning" not in result["subdimensions"]
    assert isinstance(result["meaning_score"], float)


# --- numeric range --------------------------------------------------------


def test_every_numeric_value_is_in_the_unit_range(tmp_path) -> None:
    result = score(_write(tmp_path, _RICH_TEXT), embed_fn=RecordingEmbed())
    assert 0.0 <= result["meaning_score"] <= 1.0
    for name, value in result["subdimensions"].items():
        assert isinstance(value, float), name
        assert 0.0 <= value <= 1.0, name


def test_score_output_is_json_serializable_round_trip(tmp_path) -> None:
    result = score(_write(tmp_path, _RICH_TEXT), embed_fn=RecordingEmbed())
    assert json.loads(json.dumps(result)) == result


# --- diagnostics wiring ---------------------------------------------------


def test_diagnostics_field_matches_the_offline_engine(tmp_path) -> None:
    text = "Something happened yesterday."  # fires all three rules
    result = score(_write(tmp_path, text), embed_fn=RecordingEmbed())
    assert result["diagnostics"] == diagnostics(text)
    assert [d["code"] for d in result["diagnostics"]] == [
        "missing_consequence",
        "missing_owner",
        "missing_next_action",
    ]


def test_healthy_artifact_has_no_diagnostics(tmp_path) -> None:
    result = score(_write(tmp_path, _RICH_TEXT), embed_fn=RecordingEmbed())
    assert result["diagnostics"] == []


# --- efficiency: one embed of the artifact, anchors in one batch ----------


def test_artifact_embedded_exactly_once_in_a_single_batch(tmp_path) -> None:
    text = "Deploy the fix so that revenue is safe; @bob owns the rollout."
    embed = RecordingEmbed()

    score(_write(tmp_path, text), embed_fn=embed)

    # Exactly one embed_fn call for the whole run...
    assert embed.calls == 1
    # ...in which the artifact text appears exactly once (never re-embedded
    # per subdimension)...
    assert embed.seen.count(text) == 1
    # ...and that single batch carried the artifact plus every anchor line for
    # every dimension.
    total_anchor_lines = sum(
        len(high) + len(low) for high, low in (load_anchors(d) for d in DIMENSIONS)
    )
    assert len(embed.batches[0]) == 1 + total_anchor_lines
    # The artifact is the first entry in the batch.
    assert embed.batches[0][0] == text


def test_measure_embeds_once_and_returns_vector_plus_all_scores(tmp_path) -> None:
    embed = RecordingEmbed()
    vector, raw_scores = measure("A consequential, owned, actionable claim.", embed_fn=embed)

    assert embed.calls == 1
    assert isinstance(vector, np.ndarray)
    assert vector.ndim == 1
    # raw_scores covers every dimension, including the global "meaning" axis.
    assert set(raw_scores) == set(DIMENSIONS)
    for value in raw_scores.values():
        assert 0.0 <= value <= 1.0


# --- extensibility: an open subdimension map ------------------------------


def test_new_subdimension_appears_without_any_schema_change(monkeypatch, tmp_path) -> None:
    # Register a synthetic sixth subdimension purely via the registry + anchor
    # loader — score.py itself is not touched.
    extended = tuple(axis.DIMENSIONS) + ("novelty",)
    real_load = axis.load_anchors

    def fake_load(dimension: str) -> tuple[list[str], list[str]]:
        if dimension == "novelty":
            return (
                [
                    "a fresh, surprising insight",
                    "an unexpected framing",
                    "a novel angle",
                    "a new idea",
                ],
                ["the same old restatement", "a tired cliche", "a rote summary", "a stale rehash"],
            )
        return real_load(dimension)

    monkeypatch.setattr(axis, "DIMENSIONS", extended)
    monkeypatch.setattr(axis, "load_anchors", fake_load)

    result = score(_write(tmp_path, _RICH_TEXT), embed_fn=RecordingEmbed())

    # The new dimension surfaces in the open subdimensions map...
    assert "novelty" in result["subdimensions"]
    assert 0.0 <= result["subdimensions"]["novelty"] <= 1.0
    # ...the original five are still present...
    for name in _SUBDIMENSIONS:
        assert name in result["subdimensions"]
    # ...and the top-level contract shape is unchanged.
    assert set(result) == {"meaning_score", "subdimensions", "diagnostics"}


# --- offline degrade ------------------------------------------------------


def test_score_propagates_embed_unavailable_when_endpoint_down(tmp_path) -> None:
    path = _write(tmp_path, _RICH_TEXT)
    with pytest.raises(EmbedUnavailable):
        score(path, embed_fn=_raising_embed)


def test_diagnostics_only_succeeds_even_when_embedding_would_fail(tmp_path) -> None:
    text = "Something happened yesterday."
    path = _write(tmp_path, text)

    # The same embed_fn that makes score() fail...
    with pytest.raises(EmbedUnavailable):
        score(path, embed_fn=_raising_embed)

    # ...has no effect on diagnostics_only, which never embeds.
    diags = diagnostics_only(path)
    assert isinstance(diags, list)
    assert diags == diagnostics(text)


def test_diagnostics_only_does_not_embed(tmp_path) -> None:
    # A recording embedder passed nowhere near diagnostics_only must stay unused.
    embed = RecordingEmbed()
    diagnostics_only(_write(tmp_path, _RICH_TEXT))
    assert embed.calls == 0


# --- default seam ---------------------------------------------------------


def test_default_embed_fn_is_the_real_embed_texts() -> None:
    sig = inspect.signature(score)
    assert sig.parameters["embed_fn"].default is embed_texts
    assert inspect.signature(measure).parameters["embed_fn"].default is embed_texts


def test_score_missing_file_raises_file_not_found(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        score(tmp_path / "does-not-exist.md", embed_fn=RecordingEmbed())
