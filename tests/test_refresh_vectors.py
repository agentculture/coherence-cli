"""Tests for ``scripts/refresh_meaning_vectors.py`` — the vector-count guard.

The script is not an importable package module (it lives under ``scripts/``,
outside the ``coherence`` package), so it is loaded here via
``importlib.util.spec_from_file_location`` from its on-disk path. Both cases
patch the loaded module's own ``embed_texts`` and ``RECORDED_PATH`` globals
directly, so the real fixtures/anchors are collected (deterministic, offline)
but nothing touches the network or the committed recorded-vectors fixture.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "refresh_meaning_vectors.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_meaning_vectors", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_raises_when_embed_texts_returns_fewer_vectors_than_texts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script_module()
    recorded_path = tmp_path / "recorded_vectors.json"
    monkeypatch.setattr(module, "RECORDED_PATH", recorded_path)

    def _short_embed(texts: list[str]) -> list[list[float]]:
        # Simulate a truncated response: one fewer vector than requested.
        return [[0.0] for _ in texts[:-1]]

    monkeypatch.setattr(module, "embed_texts", _short_embed)

    with pytest.raises(RuntimeError, match="expected .* got"):
        module.main()

    assert not recorded_path.exists(), "a truncated response must not be written to disk"


def test_main_happy_path_writes_recorded_file_when_counts_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script_module()
    recorded_path = tmp_path / "recorded_vectors.json"
    monkeypatch.setattr(module, "RECORDED_PATH", recorded_path)

    def _equal_embed(texts: list[str]) -> list[list[float]]:
        return [[float(i)] for i in range(len(texts))]

    monkeypatch.setattr(module, "embed_texts", _equal_embed)

    module.main()

    assert recorded_path.exists()
    recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
    assert set(recorded) == {"metadata", "vectors"}
    assert len(recorded["vectors"]) == len(module._collect_texts())


def test_main_stamps_model_tieout_metadata_from_runtime_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The recording names the embedding model/endpoint that produced it.

    This is the model tie-out: recorded geometry is only meaningful for its
    source model, so the metadata must reflect the env the refresh actually
    ran against — not a hardcoded default.
    """
    module = _load_script_module()
    recorded_path = tmp_path / "recorded_vectors.json"
    monkeypatch.setattr(module, "RECORDED_PATH", recorded_path)
    monkeypatch.setattr(module, "embed_texts", lambda texts: [[0.0] for _ in texts])
    monkeypatch.setenv("COHERENCE_EMBED_URL", "http://tieout.test:9999/v1")
    monkeypatch.setenv("COHERENCE_EMBED_MODEL", "tieout/test-model")

    module.main()

    metadata = json.loads(recorded_path.read_text(encoding="utf-8"))["metadata"]
    assert metadata["embedding_model"] == "tieout/test-model"
    assert metadata["embedding_endpoint"] == "http://tieout.test:9999/v1"
    assert metadata["recorded"]  # ISO date stamped
    assert metadata["script"] == "scripts/refresh_meaning_vectors.py"


def test_committed_recording_carries_model_tieout_metadata() -> None:
    """The committed fixture must name its source embedding model.

    Guards against silent drift: if the vectors are ever refreshed from a
    different model, the metadata changes with them (the refresh script stamps
    it), and a replay can be checked against the frame it claims.
    """
    from tests._meaning_recorded import load_recorded_metadata, recorded_vectors_present

    if not recorded_vectors_present():
        pytest.skip("recorded vectors absent")
    metadata = load_recorded_metadata()
    assert metadata is not None, "committed recording lacks the metadata tie-out block"
    assert metadata["embedding_model"], "metadata must name the source embedding model"
