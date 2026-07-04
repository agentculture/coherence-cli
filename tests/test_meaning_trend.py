"""Tests for coherence.meaning.trend — the f'/f'' series engine.

Every test here is fully OFFLINE: the embedding function is injected as a
synthetic, deterministic ``embed_fn``, so no real ``/v1/embeddings`` endpoint is
ever contacted. Two synthetic embedders are used:

* A *controlled* embedder that pins every anchor onto one shared axis and maps
  each artifact file to a chosen vector. Because every dimension's axis is the
  same direction, an artifact's score is a *known* function of its vector
  (``(cos(vec, axis) + 1) / 2``), and that same vector drives the embedding
  drift — so both the score derivatives and the drift series have exact,
  hand-computable expected values, and all subdimensions share one series.
* A *recording* hash embedder (deterministic per text) used to prove each
  artifact is embedded exactly once and to exercise the compare-vs-trend
  agreement against independently computed scores.

Acceptance criteria under test (plan task t7):

* ``trend(paths)`` with ``n >= 2`` emits per-step first differences for
  ``meaning_score``, each subdimension, and embedding drift.
* ``n >= 3`` additionally emits second differences per signal; ``n == 2`` marks
  them unavailable (``null`` with a ``reason`` string) instead of erroring.
* Differences are per-step and unitless; series are index-aligned:
  ``len(first) == n - 1`` and ``len(second) == n - 2``.
* On exactly two points, trend's first differences are identical to
  ``compare``'s ``delta`` on the same files.
"""

from __future__ import annotations

import hashlib
import inspect

import pytest

from coherence.meaning.axis import DIMENSIONS, load_anchors
from coherence.meaning.compare import compare
from coherence.meaning.embed import embed_texts
from coherence.meaning.trend import trend

_SUBDIMENSIONS = ("consequence", "agency", "causality", "affordance", "future_constraint")
_ALL_SIGNALS = ("meaning_score", *_SUBDIMENSIONS, "drift")


# --- controlled embedder: known scores + known drift ----------------------

# Vectors live in a small fixed orthonormal space. Every "high" anchor maps to
# e0 and every "low" anchor to the zero vector, so *every* dimension's axis is
# mean(high) - mean(low) == e0. An artifact mapped onto a unit basis vector then
# scores a known value: e0 -> cos +1 -> 1.0, any e_k (k>0) -> cos 0 -> 0.5,
# -e0 -> cos -1 -> 0.0. The same vectors drive the drift distances.
_DIM = 8


def _basis(index: int, sign: float = 1.0) -> list[float]:
    """Return ``sign`` times the ``index``-th standard basis vector in R^_DIM."""
    vec = [0.0] * _DIM
    vec[index] = sign
    return vec


_HIGH_VEC = _basis(0)  # e0
_LOW_VEC = [0.0] * _DIM  # zero -> axis == e0


def _make_controlled_embed(vector_map: dict[str, list[float]]):
    """Build an embed_fn giving each artifact file a chosen vector.

    Anchor lines are recognised by exact text and pinned to the shared axis;
    any other text is looked up verbatim in ``vector_map`` (its file content is
    the key), so a file's embedding — hence its meaning scores *and* its drift
    contribution — is fully controlled.
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
            else:
                out.append(list(vector_map[text]))
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


def _write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _three_point_series(tmp_path):
    """Write three files with controlled vectors and return (paths, embed_fn).

    Vectors: v0 = e0 (score 1.0), v1 = e1 (score 0.5), v2 = e1 (score 0.5).

    Score series [1.0, 0.5, 0.5] -> first [-0.5, 0.0] -> second [0.5].
    Drift: 1 - cos(e0, e1) = 1.0, then 1 - cos(e1, e1) = 0.0 -> [1.0, 0.0];
    drift is itself "first", and its second (difference) is [-1.0].
    """
    contents = ["POINT-0 content", "POINT-1 content", "POINT-2 content"]
    vectors = [_basis(0), _basis(1), _basis(1)]
    vector_map = dict(zip(contents, vectors))
    paths = [_write(tmp_path, f"p{i}.md", contents[i]) for i in range(3)]
    return paths, _make_controlled_embed(vector_map)


# --- top-level shape ------------------------------------------------------


def test_trend_returns_documented_top_level_shape(tmp_path) -> None:
    paths, embed = _three_point_series(tmp_path)
    result = trend(paths, embed_fn=embed)
    assert set(result) == {
        "n",
        "paths",
        "points",
        "per_step_drift",
        "signals",
        "second_difference_available",
    }
    assert result["n"] == 3
    assert result["paths"] == [str(p) for p in paths]
    assert set(result["signals"]) == set(_ALL_SIGNALS)


def test_points_carry_raw_meaning_and_subdimension_values(tmp_path) -> None:
    paths, embed = _three_point_series(tmp_path)
    result = trend(paths, embed_fn=embed)
    assert len(result["points"]) == 3
    for point in result["points"]:
        assert set(point) == {"meaning_score", "subdimensions"}
        assert set(point["subdimensions"]) == set(_SUBDIMENSIONS)
    # Known per-point meaning scores from the controlled vectors: [1.0, 0.5, 0.5].
    assert [p["meaning_score"] for p in result["points"]] == pytest.approx([1.0, 0.5, 0.5])


# --- index alignment: len(first)==n-1, len(second)==n-2 -------------------


def test_first_and_second_lengths_are_index_aligned(tmp_path) -> None:
    paths, embed = _three_point_series(tmp_path)
    n = len(paths)
    result = trend(paths, embed_fn=embed)
    for name in _ALL_SIGNALS:
        first = result["signals"][name]["first"]["values"]
        second = result["signals"][name]["second"]["values"]
        assert len(first) == n - 1, name
        assert len(second) == n - 2, name
    # per_step_drift is a per-step series aligned with the first differences.
    assert len(result["per_step_drift"]) == n - 1


# --- n>=3: both derivative series present with known values ---------------


def test_n3_emits_both_first_and_second_with_known_score_values(tmp_path) -> None:
    paths, embed = _three_point_series(tmp_path)
    result = trend(paths, embed_fn=embed)
    assert result["second_difference_available"] is True

    ms = result["signals"]["meaning_score"]
    assert ms["first"]["values"] == pytest.approx([-0.5, 0.0])
    assert ms["first"]["reason"] is None
    assert ms["second"]["values"] == pytest.approx([0.5])
    assert ms["second"]["reason"] is None

    # All subdimensions share the single axis, so their series match meaning's.
    for sub in _SUBDIMENSIONS:
        sig = result["signals"][sub]
        assert sig["first"]["values"] == pytest.approx([-0.5, 0.0]), sub
        assert sig["second"]["values"] == pytest.approx([0.5]), sub


# --- drift series ---------------------------------------------------------


def test_drift_series_has_known_first_and_second(tmp_path) -> None:
    paths, embed = _three_point_series(tmp_path)
    result = trend(paths, embed_fn=embed)

    # Raw per-step drift and the drift signal's "first" are the same series.
    assert result["per_step_drift"] == pytest.approx([1.0, 0.0])
    drift = result["signals"]["drift"]
    assert drift["first"]["values"] == pytest.approx([1.0, 0.0])
    # Second difference of drift = 0.0 - 1.0 = -1.0.
    assert drift["second"]["values"] == pytest.approx([-1.0])
    assert drift["second"]["reason"] is None


# --- n==2: second differences unavailable with a reason -------------------


def test_n2_first_present_second_unavailable_with_reason(tmp_path) -> None:
    contents = ["TWO-0 content", "TWO-1 content"]
    vector_map = dict(zip(contents, [_basis(0), _basis(1)]))
    paths = [_write(tmp_path, f"t{i}.md", contents[i]) for i in range(2)]
    result = trend(paths, embed_fn=_make_controlled_embed(vector_map))

    assert result["n"] == 2
    assert result["second_difference_available"] is False

    for name in _ALL_SIGNALS:
        sig = result["signals"][name]
        # First difference is present (length n-1 == 1) for every signal.
        assert len(sig["first"]["values"]) == 1, name
        # Second difference is unavailable: null values + a reason string.
        assert sig["second"]["values"] is None, name
        assert isinstance(sig["second"]["reason"], str) and sig["second"]["reason"], name

    # Known values: meaning first == 0.5 - 1.0 == -0.5; drift == [1 - cos(e0,e1)].
    assert result["signals"]["meaning_score"]["first"]["values"] == pytest.approx([-0.5])
    assert result["signals"]["drift"]["first"]["values"] == pytest.approx([1.0])


# --- compare agreement on exactly two points ------------------------------


def test_two_point_first_differences_equal_compare_delta(tmp_path) -> None:
    # General case: a deterministic hash embedder gives arbitrary but stable
    # scores. Both compare and trend route through measure with the SAME
    # embed_fn instance, so the first differences must be bit-identical.
    before = _write(tmp_path, "before.md", "An earlier version of the note.")
    after = _write(tmp_path, "after.md", "A materially different later revision.")

    embed = RecordingEmbed()
    delta = compare(before, after, embed_fn=embed)["delta"]
    result = trend([before, after], embed_fn=embed)

    assert result["signals"]["meaning_score"]["first"]["values"][0] == delta["meaning_score"]
    for sub in _SUBDIMENSIONS:
        assert result["signals"][sub]["first"]["values"][0] == delta["subdimensions"][sub], sub


# --- embed-exactly-once ---------------------------------------------------


def test_each_artifact_is_embedded_exactly_once(tmp_path) -> None:
    contents = ["ONCE-A marker", "ONCE-B marker", "ONCE-C marker", "ONCE-D marker"]
    paths = [_write(tmp_path, f"o{i}.md", contents[i]) for i in range(4)]
    embed = RecordingEmbed()

    trend(paths, embed_fn=embed)

    # measure() does exactly one embed_fn round-trip, so trend on 4 points
    # makes exactly 4 calls — never a re-embed per subdimension or per step.
    assert embed.calls == 4
    for content in contents:
        assert any(content in text for text in embed.seen), content


def test_four_point_series_alignment(tmp_path) -> None:
    # n == 4: first length 3, second length 2, for every signal.
    contents = [f"SERIES-{i}" for i in range(4)]
    vectors = [_basis(0), _basis(1), _basis(2), _basis(3)]
    vector_map = dict(zip(contents, vectors))
    paths = [_write(tmp_path, f"s{i}.md", contents[i]) for i in range(4)]
    result = trend(paths, embed_fn=_make_controlled_embed(vector_map))

    assert result["n"] == 4
    for name in _ALL_SIGNALS:
        assert len(result["signals"][name]["first"]["values"]) == 3, name
        assert len(result["signals"][name]["second"]["values"]) == 2, name


# --- guards ---------------------------------------------------------------


@pytest.mark.parametrize("paths", [[], ["only.md"]])
def test_fewer_than_two_points_raises_value_error(tmp_path, paths) -> None:
    written = [_write(tmp_path, name, "x") for name in paths]
    with pytest.raises(ValueError):
        trend(written, embed_fn=_make_controlled_embed({"x": _basis(0)}))


# --- default seam ---------------------------------------------------------


def test_default_embed_fn_is_the_real_embed_texts() -> None:
    assert inspect.signature(trend).parameters["embed_fn"].default is embed_texts
