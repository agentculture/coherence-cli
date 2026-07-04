"""Scaffold tests for the coherence.meaning package and runtime deps."""

from __future__ import annotations

import tomllib
from pathlib import Path

from coherence.meaning import EmbedUnavailable

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"


def test_embed_unavailable_is_exception() -> None:
    assert issubclass(EmbedUnavailable, Exception)


def test_embed_unavailable_has_docstring() -> None:
    assert EmbedUnavailable.__doc__
    assert len(EmbedUnavailable.__doc__) > 0


def test_pyproject_declares_numpy_and_httpx() -> None:
    data = tomllib.loads(PYPROJECT.read_text())
    deps = data["project"]["dependencies"]
    dep_names = {d.split(">=")[0].split("<")[0].split("!")[0].strip() for d in deps}
    assert "numpy" in dep_names, f"numpy not in {dep_names}"
    assert "httpx" in dep_names, f"httpx not in {dep_names}"