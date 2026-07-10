"""Tests for coherence.meaning.compare — the two-point delta engine.

Every test here is fully OFFLINE: the embedding function is injected as a
synthetic, deterministic ``embed_fn``, so no real ``/v1/embeddings`` endpoint is
ever contacted. Two synthetic embedders are used:

* A *controlled* embedder that pins every anchor onto one shared axis and maps
  the artifact onto a chosen vector, so a file's meaning scores are *known*
  (1.0 when aligned with the axis, 0.0 when anti-aligned). This makes the delta
  arithmetic checkable against exact expected values.
* A *recording* hash embedder (deterministic per text) used to prove the same
  ``embed_fn`` is threaded to *both* files and to exercise the general
  ``after - before`` arithmetic against independently computed scores.

Acceptance criteria under test (plan task t6):

* ``compare(before, after)`` returns exactly ``{before, after, delta}`` where
  ``before``/``after`` are the full :func:`score` dicts and ``delta`` carries a
  signed ``meaning_score`` plus a ``subdimensions`` map of the 5 named keys.
* ``delta = after - before`` for ``meaning_score`` and every subdimension
  (positive = the ``after`` artifact gained meaning).
* ``compare(f, f)`` of a file against itself yields all-zero deltas.
"""

from __future__ import annotations

import hashlib
import inspect

import pytest

from coherence.meaning import EmbedUnavailable
from coherence.meaning.axis import DIMENSIONS, load_anchors
from coherence.meaning.compare import compare
from coherence.meaning.embed import embed_texts
from coherence.meaning.score import score

_SUBDIMENSIONS = ("consequence", "agency", "causality", "affordance", "future_constraint")

# The three additive top-level keys the two-speed envelope adds to the meaning
# outputs (see docs/envelope.md). These assertions are relaxed to *tolerate*
# those additions while pinning the pre-existing keys/values exactly.
_ADDITIVE_KEYS = {"domain", "score_type", "frame"}


def _strip_additive(result: dict) -> dict:
    """Return ``result`` without the three additive envelope keys."""
    return {key: value for key, value in result.items() if key not in _ADDITIVE_KEYS}


# --- controlled embedder: pins every anchor onto one shared axis ----------

# Vectors live in a small fixed space. Every "high" anchor maps to _HIGH_VEC and
# every "low" anchor to _LOW_VEC, so *every* dimension's axis is the same
# direction: mean(high) - mean(low) == _HIGH_VEC. An artifact mapped onto
# _ALIGNED_VEC then scores 1.0 on every dimension (cos = +1), and _ANTI_VEC
# scores 0.0 (cos = -1). That gives files with fully known meaning scores.
_DIM = 8
_HIGH_VEC = [1.0] + [0.0] * (_DIM - 1)
_LOW_VEC = [0.0] * _DIM
_ALIGNED_VEC = [1.0] + [0.0] * (_DIM - 1)
_ANTI_VEC = [-1.0] + [0.0] * (_DIM - 1)


def _make_controlled_embed():
    """Build an embed_fn giving files *known* scores.

    Anchor lines are recognised by exact text and pinned to the shared axis;
    artifact text is mapped to :data:`_ANTI_VEC` if it contains ``"ANTI"`` (score
    0.0 everywhere) and to :data:`_ALIGNED_VEC` otherwise (score 1.0 everywhere).
    """
    high_set: set[str] = set()
    low_set: set[str] = set()
    for dimension in DIMENSIONS:
        highs, lows = load_anchors(dimension)
        high_set.update(highs)
        low_set.update(lows)

    def embed(texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            if text in high_set:
                out.append(list(_HIGH_VEC))
            elif text in low_set:
                out.append(list(_LOW_VEC))
            elif "ANTI" in text:
                out.append(list(_ANTI_VEC))
            else:
                out.append(list(_ALIGNED_VEC))
        return out

    return embed


# --- recording hash embedder: deterministic, general-purpose --------------


def _fake_vector(text: str, dim: int = 12) -> list[float]:
    """Deterministic, non-zero pseudo-embedding derived from ``text``."""
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


def _write(tmp_path, name: str, text: str) -> "object":
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --- contract shape -------------------------------------------------------


def test_compare_returns_exact_top_level_key_shape(tmp_path) -> None:
    before = _write(tmp_path, "before.md", "An aligned, meaningful claim.")
    after = _write(tmp_path, "after.md", "ANTI: a meaningless restatement.")
    result = compare(before, after, embed_fn=_make_controlled_embed())
    # Additive-tolerant: the pinned v0.5.0 top-level keys are exactly these; the
    # three additive envelope keys (domain/score_type/frame) may be added on top.
    assert set(result) - _ADDITIVE_KEYS == {"before", "after", "delta"}


def test_delta_has_exactly_meaning_score_and_subdimensions(tmp_path) -> None:
    before = _write(tmp_path, "before.md", "An aligned, meaningful claim.")
    after = _write(tmp_path, "after.md", "ANTI: a meaningless restatement.")
    result = compare(before, after, embed_fn=_make_controlled_embed())
    assert set(result["delta"]) == {"meaning_score", "subdimensions"}
    assert isinstance(result["delta"]["meaning_score"], float)
    assert isinstance(result["delta"]["subdimensions"], dict)


def test_delta_subdimensions_are_exactly_the_five_named_keys(tmp_path) -> None:
    before = _write(tmp_path, "before.md", "An aligned, meaningful claim.")
    after = _write(tmp_path, "after.md", "ANTI: a meaningless restatement.")
    result = compare(before, after, embed_fn=_make_controlled_embed())
    assert set(result["delta"]["subdimensions"]) == set(_SUBDIMENSIONS)
    for name, value in result["delta"]["subdimensions"].items():
        assert isinstance(value, float), name


def test_before_and_after_are_the_full_score_dicts(tmp_path) -> None:
    embed = _make_controlled_embed()
    before = _write(tmp_path, "before.md", "An aligned, meaningful claim.")
    after = _write(tmp_path, "after.md", "ANTI: a meaningless restatement.")
    result = compare(before, after, embed_fn=embed)
    # The before/after blocks are the clean v0.5.0 shape — exactly what score()
    # emits for each file with the additive envelope keys stripped (those keys
    # live once at the compare result's top level, not duplicated per side).
    assert result["before"] == _strip_additive(score(before, embed_fn=_make_controlled_embed()))
    assert result["after"] == _strip_additive(score(after, embed_fn=_make_controlled_embed()))
    for block in (result["before"], result["after"]):
        assert set(block) == {"meaning_score", "subdimensions", "diagnostics"}


# --- self-comparison: all-zero deltas -------------------------------------


def test_compare_file_against_itself_yields_all_zero_deltas(tmp_path) -> None:
    same = _write(
        tmp_path,
        "same.md",
        "Ship the fix so revenue is safe; @bob owns it. Next: verify counts.",
    )
    result = compare(same, same, embed_fn=RecordingEmbed())
    assert result["delta"]["meaning_score"] == 0.0
    assert all(v == 0.0 for v in result["delta"]["subdimensions"].values())
    # And the two scored blocks are identical.
    assert result["before"] == result["after"]


# --- known-score delta arithmetic -----------------------------------------


def test_delta_is_after_minus_before_with_known_scores(tmp_path) -> None:
    # before is axis-aligned -> every score 1.0; after is anti-aligned -> 0.0.
    before = _write(tmp_path, "before.md", "An aligned, meaningful claim.")
    after = _write(tmp_path, "after.md", "ANTI: a meaningless restatement.")
    result = compare(before, after, embed_fn=_make_controlled_embed())

    assert result["before"]["meaning_score"] == pytest.approx(1.0)
    assert result["after"]["meaning_score"] == pytest.approx(0.0)

    # delta = after - before = 0.0 - 1.0 = -1.0, everywhere.
    assert result["delta"]["meaning_score"] == pytest.approx(-1.0)
    for value in result["delta"]["subdimensions"].values():
        assert value == pytest.approx(-1.0)


def test_positive_delta_means_after_gained_meaning(tmp_path) -> None:
    # Swap the roles: before anti-aligned (0.0), after aligned (1.0) -> +1.0.
    before = _write(tmp_path, "before.md", "ANTI: a meaningless restatement.")
    after = _write(tmp_path, "after.md", "An aligned, meaningful claim.")
    result = compare(before, after, embed_fn=_make_controlled_embed())

    assert result["delta"]["meaning_score"] == pytest.approx(1.0)
    for value in result["delta"]["subdimensions"].values():
        assert value == pytest.approx(1.0)


def test_delta_matches_independently_computed_scores(tmp_path) -> None:
    # General case: deterministic hash embedder, arbitrary distinct files.
    before = _write(tmp_path, "before.md", "Some earlier version of the note.")
    after = _write(tmp_path, "after.md", "A quite different later revision here.")

    result = compare(before, after, embed_fn=RecordingEmbed())
    before_score = score(before, embed_fn=RecordingEmbed())
    after_score = score(after, embed_fn=RecordingEmbed())

    assert result["delta"]["meaning_score"] == pytest.approx(
        after_score["meaning_score"] - before_score["meaning_score"]
    )
    for name in _SUBDIMENSIONS:
        expected = after_score["subdimensions"][name] - before_score["subdimensions"][name]
        assert result["delta"]["subdimensions"][name] == pytest.approx(expected)


# --- embed_fn threading ---------------------------------------------------


def test_embed_fn_is_threaded_to_both_files(tmp_path) -> None:
    embed = RecordingEmbed()
    before = _write(tmp_path, "before.md", "BEFORE-MARKER earlier version.")
    after = _write(tmp_path, "after.md", "AFTER-MARKER later version.")

    compare(before, after, embed_fn=embed)

    # score() embeds once per file, so compare embeds exactly twice...
    assert embed.calls == 2
    # ...and both artifact texts rode through the injected embedder.
    assert any("BEFORE-MARKER earlier version." in t for t in embed.seen)
    assert any("AFTER-MARKER later version." in t for t in embed.seen)


def test_compare_propagates_embed_unavailable_when_endpoint_down(tmp_path) -> None:
    before = _write(tmp_path, "before.md", "An aligned, meaningful claim.")
    after = _write(tmp_path, "after.md", "ANTI: a meaningless restatement.")
    with pytest.raises(EmbedUnavailable):
        compare(before, after, embed_fn=_raising_embed)


# --- default seam ---------------------------------------------------------


def test_default_embed_fn_is_the_real_embed_texts() -> None:
    assert inspect.signature(compare).parameters["embed_fn"].default is embed_texts
