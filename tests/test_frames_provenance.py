"""Offline contract tests for ``coherence.frames.provenance``.

The frame block records which semantic coordinate frame produced an
embedding-derived measurement — this repo's spec calls scores "model-relative,
anchor-defined semantic measurements", and the frame block is the declared
gauge (see ``docs/envelope.md`` and the frames-domain requirement in
``docs/specs/2026-07-06-coherence-cli-ships-as-a-five-domain-coherence-eng.md``).

Two things this module must get right, per the build plan's acceptance
criteria for task t2:

1. ``embedding_model``/``embedding_endpoint`` are resolved from the runtime
   embed config (``COHERENCE_EMBED_URL``/``COHERENCE_EMBED_MODEL``) *at call
   time* — a monkeypatched env changes the emitted block, and the documented
   defaults (``coherence.meaning.embed.DEFAULT_EMBED_URL`` /
   ``DEFAULT_EMBED_MODEL``) appear only when the env vars are unset.
2. Absent provenance is representable as an explicit null-frame with a
   machine-readable reason, never a missing key — by delegating to
   :func:`coherence.schema.null_frame`, not reinventing it.

Fully offline: no network. The autouse ``_no_network_embed`` fixture in
``tests/conftest.py`` patches ``coherence.meaning.embed.embed_texts`` to raise
if called, which doubles as a guard here — building a frame dict must never
reach for the embeddings endpoint.
"""

from __future__ import annotations

import pytest

from coherence.frames.provenance import build_frame
from coherence.meaning.embed import DEFAULT_EMBED_MODEL, DEFAULT_EMBED_URL
from coherence.schema import build_envelope, null_frame, validate_envelope

_FRAME_KEYS = {
    "embedding_model",
    "embedding_endpoint",
    "anchor_set",
    "projection_method",
    "score_type",
}


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COHERENCE_EMBED_URL", raising=False)
    monkeypatch.delenv("COHERENCE_EMBED_MODEL", raising=False)


# --- acceptance criterion 1: runtime env resolution, at call time ----------


def test_build_frame_reflects_documented_defaults_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_env(monkeypatch)

    frame = build_frame(
        anchor_set="meaning-v1",
        projection_method="contrastive_axis",
        score_type="model_relative_anchor_defined_projection",
    )

    assert frame["embedding_model"] == DEFAULT_EMBED_MODEL
    assert frame["embedding_endpoint"] == DEFAULT_EMBED_URL


def test_build_frame_reflects_monkeypatched_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COHERENCE_EMBED_URL", "http://embed.internal:9000/v1")
    monkeypatch.setenv("COHERENCE_EMBED_MODEL", "acme/custom-embed")

    frame = build_frame(
        anchor_set="meaning-v1",
        projection_method="contrastive_axis",
        score_type="model_relative_anchor_defined_projection",
    )

    assert frame["embedding_model"] == "acme/custom-embed"
    assert frame["embedding_endpoint"] == "http://embed.internal:9000/v1"


def test_build_frame_resolves_env_at_call_time_not_import_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two calls in the same test, with the env changed between them, must
    produce two different frame blocks — proving resolution happens per-call
    rather than being cached at import or module-load time."""
    _clear_env(monkeypatch)
    first = build_frame(
        anchor_set="meaning-v1", projection_method="contrastive_axis", score_type="s"
    )
    assert first["embedding_model"] == DEFAULT_EMBED_MODEL
    assert first["embedding_endpoint"] == DEFAULT_EMBED_URL

    monkeypatch.setenv("COHERENCE_EMBED_URL", "http://other:1234/v1")
    monkeypatch.setenv("COHERENCE_EMBED_MODEL", "other/model")
    second = build_frame(
        anchor_set="meaning-v1", projection_method="contrastive_axis", score_type="s"
    )

    assert second["embedding_model"] == "other/model"
    assert second["embedding_endpoint"] == "http://other:1234/v1"
    assert first != second


def test_build_frame_never_touches_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Building a frame dict is pure env/argument assembly — it must never call
    the embeddings endpoint. The autouse conftest fixture already patches
    embed_texts to raise; this test just makes the guarantee explicit here."""
    _clear_env(monkeypatch)

    def _blocked(*_a: object, **_k: object) -> object:
        raise AssertionError("build_frame must not call embed_texts")

    monkeypatch.setattr("coherence.meaning.embed.embed_texts", _blocked)

    frame = build_frame(
        anchor_set="meaning-v1", projection_method="contrastive_axis", score_type="s"
    )
    assert frame["embedding_model"] == DEFAULT_EMBED_MODEL


# --- shape: required keys, optional axis/axes ------------------------------


def test_build_frame_has_exactly_the_required_keys_when_no_axis_given() -> None:
    frame = build_frame(
        anchor_set="meaning-v1",
        projection_method="contrastive_axis",
        score_type="model_relative_anchor_defined_projection",
    )
    assert set(frame) == _FRAME_KEYS


def test_build_frame_with_single_axis_adds_axis_key_not_axes() -> None:
    frame = build_frame(
        anchor_set="meaning-v1",
        projection_method="contrastive_axis",
        score_type="s",
        axis="valence",
    )
    assert frame["axis"] == "valence"
    assert "axes" not in frame
    assert set(frame) == _FRAME_KEYS | {"axis"}


def test_build_frame_with_multiple_axes_adds_axes_list_not_axis() -> None:
    frame = build_frame(
        anchor_set="meaning-v1",
        projection_method="contrastive_axis",
        score_type="s",
        axes=["valence", "arousal"],
    )
    assert frame["axes"] == ["valence", "arousal"]
    assert "axis" not in frame
    assert set(frame) == _FRAME_KEYS | {"axes"}


def test_build_frame_copies_axes_list_defensively() -> None:
    axes = ["valence", "arousal"]
    frame = build_frame(
        anchor_set="meaning-v1", projection_method="contrastive_axis", score_type="s", axes=axes
    )
    axes.append("tampered")
    assert frame["axes"] == ["valence", "arousal"]


def test_build_frame_rejects_axis_and_axes_together() -> None:
    with pytest.raises(ValueError):
        build_frame(
            anchor_set="meaning-v1",
            projection_method="contrastive_axis",
            score_type="s",
            axis="valence",
            axes=["valence", "arousal"],
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"anchor_set": "", "projection_method": "contrastive_axis", "score_type": "s"},
        {"anchor_set": "meaning-v1", "projection_method": "", "score_type": "s"},
        {"anchor_set": "meaning-v1", "projection_method": "contrastive_axis", "score_type": ""},
    ],
)
def test_build_frame_rejects_empty_required_strings(kwargs: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        build_frame(**kwargs)


def test_build_frame_rejects_empty_axes_list() -> None:
    with pytest.raises(ValueError):
        build_frame(
            anchor_set="meaning-v1",
            projection_method="contrastive_axis",
            score_type="s",
            axes=[],
        )


# --- frame block is envelope-compatible ------------------------------------


def test_build_frame_result_is_accepted_as_an_envelope_frame() -> None:
    frame = build_frame(
        anchor_set="meaning-v1",
        projection_method="contrastive_axis",
        score_type="model_relative_anchor_defined_projection",
        axis="valence",
    )
    envelope = build_envelope(
        domain="meaning",
        score_type="model_relative_anchor_defined_projection",
        scores={"meaning_score": 0.5},
        frame=frame,
        diagnostics=[],
    )
    assert validate_envelope(envelope) == envelope
    assert envelope["frame"] == frame


# --- acceptance criterion 2: absent provenance delegates to schema.null_frame


def test_provenance_null_frame_is_the_same_function_as_schema_null_frame() -> None:
    """Reuse, not reinvention: coherence.frames.provenance.null_frame must be
    coherence.schema.null_frame itself, not a parallel re-implementation."""
    from coherence.frames.provenance import null_frame as provenance_null_frame

    assert provenance_null_frame is null_frame


def test_null_frame_carries_machine_readable_reason_and_is_never_a_missing_key() -> None:
    from coherence.frames.provenance import null_frame as provenance_null_frame

    frame = provenance_null_frame("embedding endpoint was unreachable at measurement time")

    assert frame == null_frame("embedding endpoint was unreachable at measurement time")
    assert frame["available"] is False
    assert frame["code"] == "frame_unavailable"
    assert isinstance(frame["reason"], str) and frame["reason"]


def test_null_frame_accepted_as_envelope_frame_for_absent_provenance() -> None:
    from coherence.frames.provenance import null_frame as provenance_null_frame

    frame = provenance_null_frame("no embed endpoint configured", code="frame_unavailable")
    envelope = build_envelope(
        domain="signal",
        score_type="rule_based_heuristic",
        scores={"drift": 0.1},
        frame=frame,
        diagnostics=[],
    )
    assert validate_envelope(envelope) == envelope
    assert envelope["frame"]["available"] is False
