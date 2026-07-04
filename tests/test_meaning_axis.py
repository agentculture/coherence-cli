"""Tests for coherence.meaning.axis — anchor loading + axis math.

All vectors here are SYNTHETIC numpy arrays: no network, no real embeddings.
The acceptance criteria under test (plan task t3):

* build_axis = mean(high vectors) - mean(low vectors)
* project(vec, axis) = cosine rescaled to [0,1] via (cos + 1) / 2
* parallel -> 1.0, orthogonal -> 0.5, anti-parallel -> 0.0
* zero-norm vectors project to the neutral midpoint 0.5
* construction + projection are deterministic
* anchor files exist for the global axis plus 5 subdimensions
"""

from __future__ import annotations

import numpy as np
import pytest

from coherence.meaning import axis as axis_mod
from coherence.meaning.axis import (
    ANCHORS_DIR,
    DIMENSIONS,
    NEUTRAL_SCORE,
    build_axis,
    load_anchors,
    project,
)

# --- build_axis -----------------------------------------------------------


def test_build_axis_is_mean_high_minus_mean_low() -> None:
    high = [[2.0, 0.0, 0.0], [4.0, 0.0, 0.0]]  # mean -> [3, 0, 0]
    low = [[0.0, 2.0, 0.0], [0.0, 4.0, 0.0]]  # mean -> [0, 3, 0]
    result = build_axis(high, low)
    np.testing.assert_array_equal(result, np.array([3.0, -3.0, 0.0]))


def test_build_axis_returns_ndarray() -> None:
    result = build_axis([[1.0, 0.0]], [[0.0, 0.0]])
    assert isinstance(result, np.ndarray)


def test_build_axis_rejects_empty_sets() -> None:
    with pytest.raises(ValueError):
        build_axis([], [[1.0, 0.0]])
    with pytest.raises(ValueError):
        build_axis([[1.0, 0.0]], [])


# --- project: the three canonical directions ------------------------------


def _axis() -> np.ndarray:
    # A pure +x axis, built the real way (mean high - mean low).
    return build_axis([[2.0, 0.0, 0.0]], [[0.0, 0.0, 0.0]])


def test_project_parallel_is_one() -> None:
    ax = _axis()
    assert project([5.0, 0.0, 0.0], ax) == pytest.approx(1.0)


def test_project_orthogonal_is_half() -> None:
    ax = _axis()
    assert project([0.0, 3.0, 0.0], ax) == pytest.approx(0.5)


def test_project_antiparallel_is_zero() -> None:
    ax = _axis()
    assert project([-4.0, 0.0, 0.0], ax) == pytest.approx(0.0)


def test_project_returns_plain_float_in_unit_range() -> None:
    ax = _axis()
    val = project([1.0, 1.0, 0.0], ax)
    assert isinstance(val, float)
    assert 0.0 <= val <= 1.0


# --- project: zero-norm handling ------------------------------------------


def test_project_zero_norm_vec_is_neutral() -> None:
    ax = _axis()
    assert project([0.0, 0.0, 0.0], ax) == NEUTRAL_SCORE == 0.5


def test_project_zero_norm_axis_is_neutral() -> None:
    assert project([1.0, 2.0, 3.0], [0.0, 0.0, 0.0]) == NEUTRAL_SCORE == 0.5


# --- determinism ----------------------------------------------------------


def test_build_axis_is_deterministic() -> None:
    high = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    low = [[0.5, 0.5, 0.5], [1.5, 1.5, 1.5]]
    a1 = build_axis(high, low)
    a2 = build_axis(high, low)
    np.testing.assert_array_equal(a1, a2)


def test_project_is_deterministic() -> None:
    ax = build_axis([[1.0, 2.0, 3.0]], [[0.0, 0.0, 0.0]])
    vec = [3.0, -1.0, 2.0]
    scores = {project(vec, ax) for _ in range(10)}
    assert len(scores) == 1


# --- anchor loading -------------------------------------------------------


def test_dimensions_are_the_global_axis_plus_five_subdims() -> None:
    assert DIMENSIONS[0] == "meaning"
    assert set(DIMENSIONS) == {
        "meaning",
        "consequence",
        "agency",
        "causality",
        "affordance",
        "future_constraint",
    }
    assert len(DIMENSIONS) == 6


def test_load_anchors_finds_all_dimension_files() -> None:
    for dim in DIMENSIONS:
        high, low = load_anchors(dim)
        assert high, f"{dim} high anchors empty"
        assert low, f"{dim} low anchors empty"
        # ~4-8 example sentences per side (plan acceptance).
        assert 4 <= len(high) <= 8, f"{dim}.high has {len(high)} lines"
        assert 4 <= len(low) <= 8, f"{dim}.low has {len(low)} lines"


def test_load_anchors_lines_are_stripped_nonempty() -> None:
    high, low = load_anchors("consequence")
    for line in high + low:
        assert line == line.strip()
        assert line  # no blank lines survive


def test_load_anchors_unknown_dimension_raises() -> None:
    with pytest.raises(ValueError):
        load_anchors("no_such_dimension")


def test_anchor_dir_is_next_to_module() -> None:
    assert ANCHORS_DIR.is_dir()
    # Every declared dimension has both a .high and a .low file on disk.
    for dim in DIMENSIONS:
        assert (ANCHORS_DIR / f"{dim}.high.txt").is_file()
        assert (ANCHORS_DIR / f"{dim}.low.txt").is_file()


def test_high_and_low_anchor_sets_differ() -> None:
    # Contrastive fixtures: the high and low sets must not be identical text.
    for dim in DIMENSIONS:
        high, low = load_anchors(dim)
        assert set(high).isdisjoint(set(low)), f"{dim} high/low overlap"


def test_module_exports_public_api() -> None:
    for name in ("build_axis", "project", "load_anchors", "DIMENSIONS"):
        assert name in axis_mod.__all__
