"""Env-configured client for an OpenAI-compatible ``/v1/embeddings`` endpoint.

The client mirrors eidetic's embed gear: it POSTs ``{"model", "input"}`` to
``{COHERENCE_EMBED_URL}/embeddings`` and returns one vector per input, parsed
from the response ``data[i].embedding`` in request order.

Configuration is read from the environment *at call time* so callers (and
tests) can override it per-invocation:

- ``COHERENCE_EMBED_URL``   — base URL, default ``http://localhost:8002/v1``
- ``COHERENCE_EMBED_MODEL`` — model id, default ``Qwen/Qwen3-Embedding-0.6B``

Transport failures (connect/timeout/transport) are wrapped in
:class:`~coherence.meaning.EmbedUnavailable` with an actionable message that
names both environment variables; raw ``httpx`` errors never escape.
"""

from __future__ import annotations

import os

import httpx

from coherence.meaning import EmbedUnavailable

DEFAULT_EMBED_URL = "http://localhost:8002/v1"
DEFAULT_EMBED_MODEL = "Qwen/Qwen3-Embedding-0.6B"

# Conservative default so a missing endpoint fails fast rather than hanging.
_DEFAULT_TIMEOUT = 30.0


def _embed_url() -> str:
    """Return the configured base URL, read from the environment at call time."""
    return os.environ.get("COHERENCE_EMBED_URL", DEFAULT_EMBED_URL)


def _embed_model() -> str:
    """Return the configured model id, read from the environment at call time."""
    return os.environ.get("COHERENCE_EMBED_MODEL", DEFAULT_EMBED_MODEL)


def embed_texts(
    texts: list[str],
    *,
    client: httpx.Client | None = None,
    transport: httpx.BaseTransport | None = None,
) -> list[list[float]]:
    """Embed ``texts`` via an OpenAI-compatible embeddings endpoint.

    Args:
        texts: Inputs to embed. One vector is returned per input, order
            preserved.
        client: Optional pre-built ``httpx.Client`` to reuse. When supplied it
            is used as-is and left open for the caller to close.
        transport: Optional ``httpx.BaseTransport`` (e.g. ``httpx.MockTransport``)
            used to build a throwaway client. Ignored when ``client`` is given.

    Returns:
        A list of embedding vectors, one per input, in input order.

    Raises:
        EmbedUnavailable: The endpoint could not be reached (connection,
            timeout, or transport error). The message names both
            ``COHERENCE_EMBED_URL`` and ``COHERENCE_EMBED_MODEL``.
    """
    url = _embed_url()
    model = _embed_model()
    endpoint = f"{url.rstrip('/')}/embeddings"
    payload = {"model": model, "input": list(texts)}

    owns_client = client is None
    if client is None:
        client = httpx.Client(transport=transport, timeout=_DEFAULT_TIMEOUT)

    try:
        response = client.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
    except (httpx.ConnectError, httpx.TimeoutException, httpx.TransportError) as exc:
        raise EmbedUnavailable(
            f"Embedding endpoint unreachable at {endpoint!r}: {exc}. "
            "Is an OpenAI-compatible embeddings server running? "
            f"Set COHERENCE_EMBED_URL (currently {url!r}) to the base URL and "
            f"COHERENCE_EMBED_MODEL (currently {model!r}) to a served model."
        ) from exc
    finally:
        if owns_client:
            client.close()

    return [item["embedding"] for item in data["data"]]


__all__ = ["embed_texts", "DEFAULT_EMBED_URL", "DEFAULT_EMBED_MODEL"]
