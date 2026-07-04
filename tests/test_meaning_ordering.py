"""Falsifiability gate for the Meaning Gradient — offline, recorded-vector based.

This module is the *falsifiability check*: it asserts the Meaning Gradient does
the one thing it claims — rank a rich, actionable artifact above a vague
restatement of the same topic, and rank successive rewrites as they gain
meaning. If the score engine (or its anchors) ever stopped ordering meaning
correctly, these tests would fail. There is no ``xfail`` and no tolerance
fudge: a wrong ordering is a real failure.

It runs fully offline by replaying vectors captured from a live embed gear (see
``scripts/refresh_meaning_vectors.py``) through an exact-string-lookup
``embed_fn``. Because that recording is generated against real embedding gear
and is deliberately *not* committed, the whole module SKIPS when
``tests/fixtures/meaning/recorded_vectors.json`` is absent — CI stays green
without network, and the gate arms itself the moment the recording is present.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from coherence.meaning.score import score

from ._meaning_recorded import load_recorded_embed_fn, recorded_vectors_present

# The gate: without the recorded vectors there is nothing to replay, so skip the
# whole module rather than fail. Re-run scripts/refresh_meaning_vectors.py
# against a live embed gear to produce them and arm the falsifiability check.
pytestmark = pytest.mark.skipif(
    not recorded_vectors_present(),
    reason=(
        "recorded vectors absent — run scripts/refresh_meaning_vectors.py "
        "against a live embed gear"
    ),
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "meaning"
_SERIES = _FIXTURES / "series"


def _pairs() -> list[tuple[str, Path, Path]]:
    """Discover every ``<name>.high.txt`` / ``<name>.low.txt`` fixture pair."""
    pairs: list[tuple[str, Path, Path]] = []
    for high in sorted(_FIXTURES.glob("*.high.txt")):
        name = high.name[: -len(".high.txt")]
        low = _FIXTURES / f"{name}.low.txt"
        assert low.is_file(), f"missing low fixture for pair {name!r}"
        pairs.append((name, high, low))
    return pairs


_PAIRS = _pairs()


@pytest.fixture(scope="module")
def recorded_embed():
    """The offline exact-lookup embed_fn (only built when the module isn't skipped)."""
    return load_recorded_embed_fn()


def test_fixture_inventory_is_sane() -> None:
    """At least three pairs, and the issue-#4 auth_middleware pair, must exist."""
    names = {name for name, _, _ in _PAIRS}
    assert len(_PAIRS) >= 3, f"expected >= 3 high/low pairs, found {sorted(names)}"
    assert "auth_middleware" in names, "the issue #4 auth_middleware pair must be present"


@pytest.mark.parametrize("name,high,low", _PAIRS, ids=[p[0] for p in _PAIRS])
def test_high_outranks_low(name: str, high: Path, low: Path, recorded_embed) -> None:
    """Each high fixture scores STRICTLY above its vague low counterpart."""
    high_score = score(high, embed_fn=recorded_embed)["meaning_score"]
    low_score = score(low, embed_fn=recorded_embed)["meaning_score"]
    assert high_score > low_score, (
        f"{name}: high meaning_score {high_score:.4f} not strictly greater than "
        f"low meaning_score {low_score:.4f}"
    )


def test_rewrite_series_is_non_decreasing(recorded_embed) -> None:
    """The v1 -> v2 -> v3 rewrite series gains (never loses) meaning per step."""
    scores = [
        score(_SERIES / f"v{i}.txt", embed_fn=recorded_embed)["meaning_score"] for i in (1, 2, 3)
    ]
    assert scores[0] <= scores[1] <= scores[2], f"series meaning_score not non-decreasing: {scores}"
