"""Tests for coherence.meaning.embed — the env-configured embedding client.

These tests never touch the network: every request is served by an injected
``httpx.MockTransport`` so behaviour is deterministic and offline.
"""

from __future__ import annotations

import json

import httpx
import pytest

from coherence.meaning import EmbedUnavailable
from coherence.meaning.embed import (
    DEFAULT_EMBED_MODEL,
    DEFAULT_EMBED_URL,
    embed_texts,
)


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COHERENCE_EMBED_URL", raising=False)
    monkeypatch.delenv("COHERENCE_EMBED_MODEL", raising=False)


def test_returns_one_vector_per_input_from_mocked_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_env(monkeypatch)
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        n = len(captured["body"]["input"])  # type: ignore[index]
        data = [{"embedding": [float(i), float(i) + 0.5]} for i in range(n)]
        return httpx.Response(200, json={"data": data})

    transport = httpx.MockTransport(handler)

    vectors = embed_texts(["alpha", "beta", "gamma"], transport=transport)

    # one vector per input, order preserved
    assert vectors == [[0.0, 0.5], [1.0, 1.5], [2.0, 2.5]]
    # defaults match eidetic's embed gear
    assert captured["url"] == "http://localhost:8002/v1/embeddings"
    body = captured["body"]
    assert body["model"] == DEFAULT_EMBED_MODEL == "Qwen/Qwen3-Embedding-0.6B"
    assert body["input"] == ["alpha", "beta", "gamma"]
    assert DEFAULT_EMBED_URL == "http://localhost:8002/v1"


def test_env_var_overrides_are_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COHERENCE_EMBED_URL", "http://embed.internal:9000/v1")
    monkeypatch.setenv("COHERENCE_EMBED_MODEL", "acme/custom-embed")
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"embedding": [1.0, 2.0, 3.0]}]})

    transport = httpx.MockTransport(handler)

    vectors = embed_texts(["only"], transport=transport)

    assert vectors == [[1.0, 2.0, 3.0]]
    # request URL and model reflect the overrides, read at call time
    assert captured["url"] == "http://embed.internal:9000/v1/embeddings"
    assert captured["body"]["model"] == "acme/custom-embed"  # type: ignore[index]


def test_connect_error_raises_embed_unavailable_naming_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_env(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    transport = httpx.MockTransport(handler)

    with pytest.raises(EmbedUnavailable) as excinfo:
        embed_texts(["x"], transport=transport)

    message = str(excinfo.value)
    assert "COHERENCE_EMBED_URL" in message
    assert "COHERENCE_EMBED_MODEL" in message
    # original httpx error preserved as the cause, not leaked to the caller
    assert isinstance(excinfo.value.__cause__, httpx.ConnectError)


def test_timeout_raises_embed_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    transport = httpx.MockTransport(handler)

    with pytest.raises(EmbedUnavailable) as excinfo:
        embed_texts(["x"], transport=transport)

    message = str(excinfo.value)
    assert "COHERENCE_EMBED_URL" in message
    assert "COHERENCE_EMBED_MODEL" in message
