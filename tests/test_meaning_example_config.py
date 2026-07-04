"""Tests for examples/experiments/issue-priority.yaml — the deferred phase-3
experiment config *contract* (plan task t9).

No code path in this MVP executes the YAML; these tests only assert that the
committed config parses and that its ``features.meaning`` list names *exactly*
the fields ``coherence meaning score`` emits. That ties the doc-side contract
to the real score schema: if the emitted fields ever drift, this test fails and
the example must be updated in lockstep.

PyYAML is not a hard dependency of the runtime package, so the whole module is
skipped when ``yaml`` is unavailable rather than forcing the dependency.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from coherence.meaning.axis import DIMENSIONS  # noqa: E402  (after importorskip)

_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "experiments"
    / "issue-priority.yaml"
)

# The exact top-level field names `coherence meaning score` emits, derived from
# the live contract: the scalar `meaning_score` (the global `meaning` axis),
# every subdimension (DIMENSIONS minus the global axis), and `diagnostics`.
_EMITTED_SCORE_FIELDS = frozenset(
    {"meaning_score", "diagnostics", *(d for d in DIMENSIONS if d != "meaning")}
)


@pytest.fixture(scope="module")
def config() -> dict:
    return yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))


def test_example_config_exists_and_parses(config: dict) -> None:
    assert isinstance(config, dict)


def test_config_has_the_four_documented_sections(config: dict) -> None:
    for section in ("ratings", "outcomes", "features", "metrics"):
        assert section in config, section


def test_features_meaning_lists_exactly_the_emitted_score_fields(config: dict) -> None:
    meaning_features = config["features"]["meaning"]
    assert set(meaning_features) == set(_EMITTED_SCORE_FIELDS)
    # No accidental duplicates in the committed list.
    assert len(meaning_features) == len(set(meaning_features))


def test_ratings_and_outcomes_are_per_issue_rows(config: dict) -> None:
    for row in config["ratings"]:
        assert "id" in row
    for row in config["outcomes"]:
        assert "id" in row
