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
    _DEFAULT_TIMEOUT,
    DEFAULT_EMBED_MODEL,
    DEFAULT_EMBED_URL,
    _embed_timeout,
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


def test_embed_timeout_defaults_and_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COHERENCE_EMBED_TIMEOUT", raising=False)
    assert _embed_timeout() == _DEFAULT_TIMEOUT
    # raise it for gears that lazy-load the model on the first request
    monkeypatch.setenv("COHERENCE_EMBED_TIMEOUT", "120")
    assert _embed_timeout() == 120.0
    # a malformed value falls back to the default rather than erroring
    monkeypatch.setenv("COHERENCE_EMBED_TIMEOUT", "not-a-number")
    assert _embed_timeout() == _DEFAULT_TIMEOUT


@pytest.mark.parametrize("raw", ["0", "-5", "nan", "inf"])
def test_embed_timeout_rejects_non_positive_and_non_finite(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    # Zero/negative/non-finite values are meaningless as an httpx timeout and
    # would fail obscurely at request time, so they fall back to the default.
    monkeypatch.setenv("COHERENCE_EMBED_TIMEOUT", raw)
    assert _embed_timeout() == _DEFAULT_TIMEOUT


# --- HTTP-status and malformed-response errors ---------------------------


def test_500_response_raises_embed_unavailable_naming_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_env(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "internal server error"})

    transport = httpx.MockTransport(handler)

    with pytest.raises(EmbedUnavailable) as excinfo:
        embed_texts(["x"], transport=transport)

    message = str(excinfo.value)
    assert "COHERENCE_EMBED_URL" in message
    assert "COHERENCE_EMBED_MODEL" in message
    assert isinstance(excinfo.value.__cause__, httpx.HTTPStatusError)


def test_401_response_raises_embed_unavailable_naming_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_env(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    transport = httpx.MockTransport(handler)

    with pytest.raises(EmbedUnavailable) as excinfo:
        embed_texts(["x"], transport=transport)

    message = str(excinfo.value)
    assert "COHERENCE_EMBED_URL" in message
    assert "COHERENCE_EMBED_MODEL" in message
    assert isinstance(excinfo.value.__cause__, httpx.HTTPStatusError)


def test_malformed_body_missing_embedding_key_raises_embed_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_env(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{}]})

    transport = httpx.MockTransport(handler)

    with pytest.raises(EmbedUnavailable) as excinfo:
        embed_texts(["x"], transport=transport)

    message = str(excinfo.value)
    assert "COHERENCE_EMBED_URL" in message
    assert "COHERENCE_EMBED_MODEL" in message
    assert isinstance(excinfo.value.__cause__, KeyError)


def test_malformed_body_missing_data_key_raises_embed_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_env(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)

    with pytest.raises(EmbedUnavailable) as excinfo:
        embed_texts(["x"], transport=transport)

    message = str(excinfo.value)
    assert "COHERENCE_EMBED_URL" in message
    assert "COHERENCE_EMBED_MODEL" in message
    assert isinstance(excinfo.value.__cause__, KeyError)
