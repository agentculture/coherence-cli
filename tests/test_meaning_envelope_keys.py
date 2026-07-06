"""Additive two-speed envelope keys on the meaning outputs (plan task t10).

The shipped ``coherence meaning score/compare/trend`` JSON keeps its pinned
v0.5.0 shape and GAINS exactly three additive top-level keys — ``domain``,
``score_type``, and ``frame`` — while every pre-existing key stays
byte-identical (the "two-speed envelope" rule; see ``docs/envelope.md``).

Three acceptance criteria are exercised here, all fully OFFLINE:

1. ``score --json`` output carries ``domain == "meaning"``, a ``score_type``
   string, and a ``frame`` block that reports the *runtime-resolved*
   endpoint/model/anchor-set/projection — proven by monkeypatching
   ``COHERENCE_EMBED_URL`` / ``COHERENCE_EMBED_MODEL`` and watching the frame
   follow the env (``coherence.frames.provenance.build_frame`` resolves them at
   call time).
2. Golden SUBSET test: every pre-existing key of score/compare/trend is
   byte-identical to the v0.5.0 shape. Computed on the committed recorded
   vectors, the three new keys are stripped and the remainder is deep-equal to
   an independent v0.5.0 reconstruction — so the three keys are the ONLY
   additions and no pre-existing value changed. For ``compare``/``trend`` there
   is exactly ONE top-level frame block for the whole result (the before/after
   blocks and the per-point blocks stay clean v0.5.0).
3. Offline-diagnostics path: with the embed endpoint unreachable,
   ``offline_result`` emits an explicit :func:`coherence.schema.null_frame`
   with a machine-readable reason, never a fabricated embedding frame — and
   ``score`` still raises ``EmbedUnavailable`` (the exit-2 path is preserved,
   so it never ships a fabricated frame either).
"""

from __future__ import annotations

import json
from functools import partial
from pathlib import Path

import pytest

from coherence.cli import main
from coherence.meaning import EmbedUnavailable
from coherence.meaning.axis import DIMENSIONS
from coherence.meaning.compare import compare
from coherence.meaning.diagnostics import diagnostics
from coherence.meaning.score import measure, offline_result, score
from coherence.meaning.trend import (
    _cosine_distance,
    _derivatives_from_drift,
    _derivatives_from_levels,
    trend,
)

from ._meaning_recorded import load_recorded_embed_fn, recorded_vectors_present
from ._meaning_synthetic import synthetic_embed_fn

# The three ADDITIVE top-level keys the two-speed envelope adds to meaning.
_NEW_KEYS = {"domain", "score_type", "frame"}

# The pinned contract values (asserted as literals so an accidental change to
# any of them fails loudly rather than silently redefining the frame).
_DOMAIN = "meaning"
_SCORE_TYPE = "model_relative_anchor_defined_projection"
_ANCHOR_SET = "coherence-cli meaning anchors v1"
_PROJECTION_METHOD = "mean(high) - mean(low), cosine projection"
_OFFLINE_FRAME_CODE = "embed_endpoint_unreachable"

_SUBDIMENSIONS = ("consequence", "agency", "causality", "affordance", "future_constraint")

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "meaning"
_FILE_A = _FIXTURES / "auth_middleware.high.txt"
_FILE_B = _FIXTURES / "auth_middleware.low.txt"
_FILE_C = _FIXTURES / "payment_webhook.high.txt"

_recorded = pytest.mark.skipif(
    not recorded_vectors_present(),
    reason=(
        "recorded vectors absent — run scripts/refresh_meaning_vectors.py "
        "against a live embed gear"
    ),
)


def _raising_embed(texts: list[str]) -> list[list[float]]:
    """A synthetic ``embed_fn`` that simulates an unreachable endpoint."""
    raise EmbedUnavailable("embedding endpoint unreachable (test stub)")


# --- v0.5.0 reference reconstructions (the "golden" the subset is compared to) --
#
# Each rebuilds the pinned pre-v0.5.0 shape from the SAME primitives the engines
# use internally (``measure``/``diagnostics`` and, for trend, its own unchanged
# derivative helpers), so the comparison is bit-identical when the change is
# purely additive.


def _v050_score(path: Path, embed_fn) -> dict:
    text = path.read_text(encoding="utf-8")
    _vec, raw = measure(text, embed_fn=embed_fn)
    subs = {dim: raw[dim] for dim in DIMENSIONS if dim != "meaning"}
    return {
        "meaning_score": raw["meaning"],
        "subdimensions": subs,
        "diagnostics": diagnostics(text),
    }


def _v050_compare(before: Path, after: Path, embed_fn) -> dict:
    before_score = _v050_score(before, embed_fn)
    after_score = _v050_score(after, embed_fn)
    delta = {
        "meaning_score": after_score["meaning_score"] - before_score["meaning_score"],
        "subdimensions": {
            name: after_score["subdimensions"][name] - before_score["subdimensions"][name]
            for name in after_score["subdimensions"]
        },
    }
    return {"before": before_score, "after": after_score, "delta": delta}


def _v050_trend(paths: list[Path], embed_fn) -> dict:
    vectors = []
    meaning_levels: list[float] = []
    subdim_levels: dict[str, list[float]] = {sub: [] for sub in _SUBDIMENSIONS}
    points: list[dict] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        vec, raw = measure(text, embed_fn=embed_fn)
        vectors.append(vec)
        meaning_levels.append(raw["meaning"])
        point_subs = {sub: raw[sub] for sub in _SUBDIMENSIONS}
        for sub in _SUBDIMENSIONS:
            subdim_levels[sub].append(raw[sub])
        points.append({"meaning_score": raw["meaning"], "subdimensions": point_subs})
    n = len(paths)
    per_step_drift = [_cosine_distance(vectors[i], vectors[i + 1]) for i in range(n - 1)]
    signals = {"meaning_score": _derivatives_from_levels(meaning_levels, n)}
    for sub in _SUBDIMENSIONS:
        signals[sub] = _derivatives_from_levels(subdim_levels[sub], n)
    signals["drift"] = _derivatives_from_drift(per_step_drift, n)
    return {
        "n": n,
        "paths": [str(path) for path in paths],
        "points": points,
        "per_step_drift": per_step_drift,
        "signals": signals,
        "second_difference_available": n >= 3,
    }


def _strip_new_keys(result: dict) -> dict:
    return {key: value for key, value in result.items() if key not in _NEW_KEYS}


# --- criterion 1: domain / score_type / runtime-resolved frame ---------------


def test_score_gains_domain_score_type_and_runtime_frame(monkeypatch) -> None:
    monkeypatch.setenv("COHERENCE_EMBED_URL", "http://embed.test:9999/v1")
    monkeypatch.setenv("COHERENCE_EMBED_MODEL", "test/Custom-Embedding-Model")

    result = score(_FILE_A, embed_fn=synthetic_embed_fn)

    assert result["domain"] == _DOMAIN
    assert isinstance(result["score_type"], str)
    assert result["score_type"] == _SCORE_TYPE

    frame = result["frame"]
    # The frame follows the runtime env, resolved at call time.
    assert frame["embedding_endpoint"] == "http://embed.test:9999/v1"
    assert frame["embedding_model"] == "test/Custom-Embedding-Model"
    assert frame["anchor_set"] == _ANCHOR_SET
    assert frame["projection_method"] == _PROJECTION_METHOD
    assert frame["score_type"] == _SCORE_TYPE
    # Axes are the axis names actually scored: meaning + the five subdimensions.
    assert frame["axes"] == list(DIMENSIONS)


def test_frame_follows_the_env_at_call_time(monkeypatch) -> None:
    monkeypatch.setenv("COHERENCE_EMBED_URL", "http://first.test:1/v1")
    monkeypatch.setenv("COHERENCE_EMBED_MODEL", "first/model")
    first = score(_FILE_A, embed_fn=synthetic_embed_fn)["frame"]
    assert first["embedding_endpoint"] == "http://first.test:1/v1"
    assert first["embedding_model"] == "first/model"

    # Re-point the env; the next frame reflects the new runtime config.
    monkeypatch.setenv("COHERENCE_EMBED_URL", "http://second.test:2/v1")
    monkeypatch.setenv("COHERENCE_EMBED_MODEL", "second/model")
    second = score(_FILE_A, embed_fn=synthetic_embed_fn)["frame"]
    assert second["embedding_endpoint"] == "http://second.test:2/v1"
    assert second["embedding_model"] == "second/model"


def test_cli_score_json_carries_the_additive_envelope_keys(
    capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COHERENCE_EMBED_URL", "http://cli.test:8080/v1")
    monkeypatch.setenv("COHERENCE_EMBED_MODEL", "cli/model")
    # Run the real engine end-to-end, swapping only the network embedder.
    monkeypatch.setattr(
        "coherence.cli._commands.meaning.score",
        partial(score, embed_fn=synthetic_embed_fn),
    )
    rc = main(["meaning", "score", str(_FILE_A), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["domain"] == _DOMAIN
    assert payload["score_type"] == _SCORE_TYPE
    assert payload["frame"]["embedding_endpoint"] == "http://cli.test:8080/v1"
    assert payload["frame"]["embedding_model"] == "cli/model"
    # Pre-existing keys still present and untouched by the CLI pass-through.
    assert isinstance(payload["meaning_score"], float)
    assert set(payload["subdimensions"]) == set(_SUBDIMENSIONS)


def test_compare_and_trend_carry_one_top_level_frame(monkeypatch) -> None:
    monkeypatch.setenv("COHERENCE_EMBED_URL", "http://shared.test:7/v1")
    monkeypatch.setenv("COHERENCE_EMBED_MODEL", "shared/model")

    cmp_result = compare(_FILE_A, _FILE_B, embed_fn=synthetic_embed_fn)
    assert cmp_result["domain"] == _DOMAIN
    assert cmp_result["score_type"] == _SCORE_TYPE
    assert cmp_result["frame"]["embedding_endpoint"] == "http://shared.test:7/v1"
    assert cmp_result["frame"]["axes"] == list(DIMENSIONS)
    # ONE top-level frame for the whole result; the before/after sides stay clean.
    assert "frame" not in cmp_result["before"]
    assert "frame" not in cmp_result["after"]
    assert set(cmp_result["before"]) == {"meaning_score", "subdimensions", "diagnostics"}

    tr_result = trend([_FILE_A, _FILE_B, _FILE_C], embed_fn=synthetic_embed_fn)
    assert tr_result["domain"] == _DOMAIN
    assert tr_result["score_type"] == _SCORE_TYPE
    assert tr_result["frame"]["embedding_endpoint"] == "http://shared.test:7/v1"
    assert tr_result["frame"]["axes"] == list(DIMENSIONS)
    # ONE top-level frame; the per-point blocks stay clean v0.5.0 (no frame each).
    for point in tr_result["points"]:
        assert set(point) == {"meaning_score", "subdimensions"}


# --- criterion 2: golden subset — pre-existing keys byte-identical -----------


@_recorded
def test_score_pre_existing_keys_are_byte_identical_to_v050() -> None:
    embed_fn = load_recorded_embed_fn()
    live = score(_FILE_A, embed_fn=embed_fn)

    assert _NEW_KEYS <= set(live), "the three additive keys must be present"
    stripped = _strip_new_keys(live)
    # The three new keys are the ONLY additions; every other value is unchanged.
    assert stripped == _v050_score(_FILE_A, embed_fn)
    assert set(stripped) == {"meaning_score", "subdimensions", "diagnostics"}


@_recorded
def test_compare_pre_existing_keys_are_byte_identical_to_v050() -> None:
    embed_fn = load_recorded_embed_fn()
    live = compare(_FILE_A, _FILE_B, embed_fn=embed_fn)

    assert _NEW_KEYS <= set(live)
    stripped = _strip_new_keys(live)
    assert stripped == _v050_compare(_FILE_A, _FILE_B, embed_fn)
    assert set(stripped) == {"before", "after", "delta"}


@_recorded
def test_trend_pre_existing_keys_are_byte_identical_to_v050() -> None:
    embed_fn = load_recorded_embed_fn()
    paths = [_FILE_A, _FILE_B, _FILE_C]
    live = trend(paths, embed_fn=embed_fn)

    assert _NEW_KEYS <= set(live)
    stripped = _strip_new_keys(live)
    assert stripped == _v050_trend(paths, embed_fn)
    assert set(stripped) == {
        "n",
        "paths",
        "points",
        "per_step_drift",
        "signals",
        "second_difference_available",
    }


# --- criterion 3: offline path emits an explicit null-frame, never fabricated -


def test_offline_result_emits_explicit_null_frame_with_reason() -> None:
    result = offline_result(_FILE_A)

    assert result["domain"] == _DOMAIN
    assert isinstance(result["score_type"], str) and result["score_type"] == _SCORE_TYPE

    frame = result["frame"]
    # An explicit null-frame with a machine-readable reason — never fabricated.
    assert frame["available"] is False
    assert frame["code"] == _OFFLINE_FRAME_CODE
    assert isinstance(frame["reason"], str) and frame["reason"]
    # No endpoint/model was reached, so none is claimed.
    assert "embedding_endpoint" not in frame
    assert "embedding_model" not in frame

    # The always-available rule diagnostics still ran offline.
    assert isinstance(result["diagnostics"], list)
    assert result["diagnostics"] == diagnostics(_FILE_A.read_text(encoding="utf-8"))


def test_score_does_not_fabricate_a_frame_when_endpoint_unreachable() -> None:
    # The --json / text exit-2 path is preserved: score() raises rather than
    # emitting any result dict, so it never ships a fabricated frame.
    with pytest.raises(EmbedUnavailable):
        score(_FILE_A, embed_fn=_raising_embed)
