"""Offline contract tests for ``coherence.signal.resonance`` — the pairwise
alignment engine over the source-agnostic series schema.

The spec decision under test is deliberate and central: resonance and
interference are the SAME metric read by its sign, not two engines. Every test
here drives the one public :func:`~coherence.signal.resonance.resonance`
function and inspects the sign/magnitude of its output — there is no separate
"interference" code path to test in parallel.

Two families of proof:

* **Sign-carries-meaning** — fields that move together earn a positive
  ("resonance") pair; fields that move oppositely earn a negative
  ("interference") pair; a sign-symmetry test confirms both come from the
  identical computation by negating one field and checking the alignment
  flips sign with unchanged magnitude.
* **No fabricated correlations** — a constant field (zero variance) or a pair
  with too few common points never produces a NaN or a fabricated number; it
  is excluded from ``pairs`` and named in ``diagnostics`` instead.
"""

from __future__ import annotations

import math

from coherence.signal.resonance import (
    CODE_CONSTANT_FIELD,
    CODE_NON_FINITE_CORRELATION,
    CODE_TOO_FEW_COMMON_POINTS,
    MIN_COMMON_POINTS,
    NEUTRAL_BAND,
    RELATION_INTERFERENCE,
    RELATION_NEUTRAL,
    RELATION_RESONANCE,
    resonance,
)
from coherence.signal.schema import Series, SeriesPoint, load_series

# --- helpers ----------------------------------------------------------------


def _point(pid: str, index: int, values: dict) -> dict:
    return {"id": pid, "index": index, "values": values}


def _series(points: list[dict]) -> dict:
    return {"points": points}


def _pair(result: dict, a: str, b: str) -> dict:
    """Return the pair entry for (a, b) in either stored order, or fail."""
    for pair in result["pairs"]:
        if {pair["a"], pair["b"]} == {a, b}:
            return pair
    raise AssertionError(f"no pair for {a!r}/{b!r} in {result['pairs']!r}")


def _codes(result: dict) -> set[str]:
    return {d["code"] for d in result["diagnostics"]}


# --- acceptance 1: sign carries the meaning, one code path -----------------


def test_two_rising_fields_yield_positive_resonance() -> None:
    """Fields that rise together reinforce: positive alignment, 'resonance'."""
    raw = _series([_point(f"p{i}", i, {"a": float(i), "b": float(i) * 2.0}) for i in range(5)])
    series = load_series(raw)

    result = resonance(series)

    pair = _pair(result, "a", "b")
    assert pair["alignment"] > 0.0
    assert pair["relation"] == RELATION_RESONANCE


def test_one_rising_one_falling_yields_negative_interference() -> None:
    """Fields that move oppositely conflict: negative alignment, 'interference'."""
    raw = _series([_point(f"p{i}", i, {"a": float(i), "b": -float(i)}) for i in range(5)])
    series = load_series(raw)

    result = resonance(series)

    pair = _pair(result, "a", "b")
    assert pair["alignment"] < 0.0
    assert pair["relation"] == RELATION_INTERFERENCE


def test_relation_is_derived_from_the_sign_of_the_alignment_field() -> None:
    """``relation`` is not an independent judgment call — it tracks ``alignment``'s sign."""
    raw = _series(
        [_point(f"p{i}", i, {"a": float(i), "b": float(i) * 2.0, "c": -float(i)}) for i in range(5)]
    )
    series = load_series(raw)

    result = resonance(series)

    for pair in result["pairs"]:
        if pair["alignment"] > NEUTRAL_BAND:
            assert pair["relation"] == RELATION_RESONANCE
        elif pair["alignment"] < -NEUTRAL_BAND:
            assert pair["relation"] == RELATION_INTERFERENCE
        else:
            assert pair["relation"] == RELATION_NEUTRAL


def test_sign_symmetry_negating_one_field_flips_sign_same_magnitude() -> None:
    """Correlating (x, y) and (x, -y + constant) yields alignments of opposite
    sign and equal magnitude — the same code path run on a negated input, not a
    different one for "interference".
    """
    xs = [0.0, 1.0, 2.0, 4.0, 5.0, 6.5, 9.0]
    ys = [1.0, 2.0, 1.5, 3.0, 2.5, 4.0, 3.5]  # not perfectly correlated on purpose
    raw_pos = _series([_point(f"p{i}", i, {"x": xs[i], "y": ys[i]}) for i in range(len(xs))])
    raw_neg = _series(
        [_point(f"p{i}", i, {"x": xs[i], "y_flipped": -ys[i] + 10.0}) for i in range(len(xs))]
    )

    pos_alignment = _pair(resonance(load_series(raw_pos)), "x", "y")["alignment"]
    neg_alignment = _pair(resonance(load_series(raw_neg)), "x", "y_flipped")["alignment"]

    assert pos_alignment > 0.0
    assert neg_alignment < 0.0
    assert math.isclose(pos_alignment, -neg_alignment, abs_tol=1e-9)


def test_perfectly_anticorrelated_fields_are_close_to_minus_one() -> None:
    raw = _series([_point(f"p{i}", i, {"a": float(i), "b": 10.0 - float(i)}) for i in range(6)])
    series = load_series(raw)

    pair = _pair(resonance(series), "a", "b")

    assert math.isclose(pair["alignment"], -1.0, abs_tol=1e-9)
    assert pair["relation"] == RELATION_INTERFERENCE


def test_perfectly_correlated_fields_are_close_to_plus_one() -> None:
    raw = _series(
        [_point(f"p{i}", i, {"a": float(i), "b": 3.0 * float(i) + 1.0}) for i in range(6)]
    )
    series = load_series(raw)

    pair = _pair(resonance(series), "a", "b")

    assert math.isclose(pair["alignment"], 1.0, abs_tol=1e-9)
    assert pair["relation"] == RELATION_RESONANCE


# --- acceptance 2: no fabricated correlations, ever -------------------------


def test_constant_field_is_excluded_with_diagnostic_not_nan() -> None:
    raw = _series([_point(f"p{i}", i, {"a": float(i), "flat": 5.0}) for i in range(6)])
    series = load_series(raw)

    result = resonance(series)

    assert not any({"a", "flat"} == {p["a"], p["b"]} for p in result["pairs"])
    assert CODE_CONSTANT_FIELD in _codes(result)
    # No NaNs anywhere in the surviving pairs (belt-and-suspenders: even
    # surviving pairs must never carry a NaN alignment).
    for pair in result["pairs"]:
        assert not math.isnan(pair["alignment"])


def test_both_fields_constant_is_excluded_with_diagnostic() -> None:
    raw = _series([_point(f"p{i}", i, {"flat_a": 1.0, "flat_b": 2.0}) for i in range(6)])
    series = load_series(raw)

    result = resonance(series)

    assert result["pairs"] == []
    assert CODE_CONSTANT_FIELD in _codes(result)


def test_too_few_common_points_excluded_with_diagnostic() -> None:
    """Fewer than MIN_COMMON_POINTS shared points is excluded, not correlated."""
    assert MIN_COMMON_POINTS >= 3
    raw = _series(
        [
            _point("p0", 0, {"a": 1.0, "b": 2.0}),
            _point("p1", 1, {"a": 2.0}),  # 'b' missing here
            _point("p2", 2, {"b": 4.0}),  # 'a' missing here
        ]
    )
    series = load_series(raw)

    result = resonance(series)

    assert result["pairs"] == []
    assert CODE_TOO_FEW_COMMON_POINTS in _codes(result)


def test_fields_present_on_disjoint_points_never_pair() -> None:
    """Two fields that never co-occur on any point: 0 common points, excluded."""
    raw = _series(
        [
            _point("p0", 0, {"a": 1.0}),
            _point("p1", 1, {"a": 2.0}),
            _point("p2", 2, {"b": 3.0}),
            _point("p3", 3, {"b": 4.0}),
        ]
    )
    series = load_series(raw)

    result = resonance(series)

    assert result["pairs"] == []
    assert CODE_TOO_FEW_COMMON_POINTS in _codes(result)


def test_near_zero_correlation_is_labeled_neutral_within_band() -> None:
    """A pair whose alignment falls inside the neutral band is neither
    resonance nor interference."""
    raw = _series(
        [
            _point("p0", 0, {"a": 0.0, "b": 1.0}),
            _point("p1", 1, {"a": 1.0, "b": -1.0}),
            _point("p2", 2, {"a": 2.0, "b": -1.0}),
            _point("p3", 3, {"a": 3.0, "b": -1.0}),
            _point("p4", 4, {"a": 4.0, "b": -1.0}),
            _point("p5", 5, {"a": 5.0, "b": 1.0}),
        ]
    )
    series = load_series(raw)

    pair = _pair(resonance(series), "a", "b")

    assert abs(pair["alignment"]) <= NEUTRAL_BAND
    assert pair["relation"] == RELATION_NEUTRAL


def test_no_fields_yields_empty_pairs_and_no_crash() -> None:
    series = load_series(_series([_point("p0", 0, {}), _point("p1", 1, {})]))

    result = resonance(series)

    assert result == {"pairs": [], "diagnostics": []}


def test_single_field_yields_no_pairs() -> None:
    raw = _series([_point(f"p{i}", i, {"only": float(i)}) for i in range(5)])
    series = load_series(raw)

    result = resonance(series)

    assert result["pairs"] == []


def test_result_shape_has_pairs_and_diagnostics_keys() -> None:
    raw = _series([_point(f"p{i}", i, {"a": float(i), "b": float(i) * 2.0}) for i in range(4)])
    result = resonance(load_series(raw))

    assert set(result.keys()) == {"pairs", "diagnostics"}
    assert isinstance(result["pairs"], list)
    assert isinstance(result["diagnostics"], list)
    for pair in result["pairs"]:
        assert set(pair.keys()) >= {"a", "b", "alignment", "relation"}


def test_nan_poisoned_field_is_excluded_with_diagnostic_never_nan_output() -> None:
    """``float('nan')`` is a legitimate ``float`` (the schema loader lets it
    through as numeric), so the engine itself must guard against it: a
    NaN-poisoned pair must never surface a NaN alignment — it is excluded with
    a diagnostic instead, same as any other unusable pair.
    """
    series = Series(
        points=[
            SeriesPoint(id="p0", index=0, values={"a": 1.0, "b": 2.0}),
            SeriesPoint(id="p1", index=1, values={"a": 2.0, "b": float("nan")}),
            SeriesPoint(id="p2", index=2, values={"a": 3.0, "b": 3.0}),
        ]
    )

    result = resonance(series)

    assert not any({"a", "b"} == {p["a"], p["b"]} for p in result["pairs"])
    assert CODE_NON_FINITE_CORRELATION in _codes(result)
    for pair in result["pairs"]:
        assert not math.isnan(pair["alignment"])
