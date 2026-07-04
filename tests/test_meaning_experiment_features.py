"""The phase-3 experiment config's meaning features are all emitted by ``score``.

``examples/experiments/issue-priority.yaml`` documents (issue #4) that every
field it lists under ``features.meaning`` is already produced by
``coherence meaning score <file> --json`` today. This test enforces that promise
directly: it parses the YAML and asserts every named meaning feature is present
in a real ``score(...)`` output (produced offline with the synthetic embedder),
so the deferred experiment's contract can never silently drift from the engine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from coherence.meaning.score import score

from ._meaning_synthetic import synthetic_embed_fn

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG = _REPO_ROOT / "examples" / "experiments" / "issue-priority.yaml"
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "meaning" / "auth_middleware.high.txt"


def _meaning_features() -> list[str]:
    config = yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))
    features = config["features"]["meaning"]
    assert isinstance(features, list) and features, "features.meaning must be a non-empty list"
    return features


def test_every_declared_meaning_feature_is_scored() -> None:
    features = _meaning_features()
    result = score(_FIXTURE, embed_fn=synthetic_embed_fn)

    # A score() output surfaces meaning_score and diagnostics at the top level,
    # and the five subdimensions inside the subdimensions map.
    available = {"meaning_score", "diagnostics", *result["subdimensions"]}

    missing = [feature for feature in features if feature not in available]
    assert not missing, f"features.meaning names fields score() does not emit: {missing}"


def test_config_names_the_expected_meaning_surface() -> None:
    """Guard the config against silently dropping a documented feature."""
    features = set(_meaning_features())
    expected = {
        "meaning_score",
        "consequence",
        "agency",
        "causality",
        "affordance",
        "future_constraint",
        "diagnostics",
    }
    assert features == expected, f"features.meaning drifted from the documented set: {features}"
