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
    assert len(recorded) == len(module._collect_texts())
