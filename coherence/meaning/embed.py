"""Env-configured client for an OpenAI-compatible ``/v1/embeddings`` endpoint.

The client mirrors eidetic's embed gear: it POSTs ``{"model", "input"}`` to
``{COHERENCE_EMBED_URL}/embeddings`` and returns one vector per input, parsed
from the response ``data[i].embedding`` in request order.

Configuration is read from the environment *at call time* so callers (and
tests) can override it per-invocation:

- ``COHERENCE_EMBED_URL``     — base URL, default ``http://localhost:8002/v1``
- ``COHERENCE_EMBED_MODEL``   — model id, default ``Qwen/Qwen3-Embedding-0.6B``
- ``COHERENCE_EMBED_TIMEOUT`` — request timeout in seconds, default ``30`` (raise
  it for gears that lazy-load the model on the first request)

Transport failures (connect/timeout/transport) are wrapped in
:class:`~coherence.meaning.EmbedUnavailable` with an actionable message that
names both environment variables; raw ``httpx`` errors never escape.

Reference deployment: the lobes gateway serves an ``embedder`` role, discoverable
via ``GET /capabilities`` (lobes-cli >= 0.38 advertises a client-reachable endpoint
per role). Consumers such as colleague resolve the endpoint from lobes and inject
``COHERENCE_EMBED_URL`` / ``COHERENCE_EMBED_MODEL`` when armed.

Each meaning score is a model-relative, anchor-defined measurement: the embedding
model and anchors constitute the score's reference frame (gauge). A score carries
no model-independent semantics — it is a semantic measurement declared relative to
the chosen model and anchor set (issues #10, #11).
"""

from __future__ import annotations

import math
import os

import httpx

from coherence.meaning import EmbedUnavailable

DEFAULT_EMBED_URL = "http://localhost:8002/v1"
DEFAULT_EMBED_MODEL = "Qwen/Qwen3-Embedding-0.6B"

# Conservative default so a missing endpoint fails fast rather than hanging.
# Overridable via COHERENCE_EMBED_TIMEOUT for gears that lazy-load the model on
# first request (a cold start can exceed the default).
_DEFAULT_TIMEOUT = 30.0


def _embed_url() -> str:
    """Return the configured base URL, read from the environment at call time."""
    return os.environ.get("COHERENCE_EMBED_URL", DEFAULT_EMBED_URL)


def _embed_model() -> str:
    """Return the configured model id, read from the environment at call time."""
    return os.environ.get("COHERENCE_EMBED_MODEL", DEFAULT_EMBED_MODEL)


def _embed_timeout() -> float:
    """Return the request timeout (seconds), read from the environment at call time.

    Defaults to ``_DEFAULT_TIMEOUT``; raise ``COHERENCE_EMBED_TIMEOUT`` for embed
    gears that load the model lazily on the first request. A malformed value falls
    back to the default rather than erroring.
    """
    raw = os.environ.get("COHERENCE_EMBED_TIMEOUT")
    if raw is None:
        return _DEFAULT_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT
    # Reject non-finite (nan/inf) and non-positive values: they are meaningless
    # as an httpx timeout and would fail obscurely at request time.
    if not math.isfinite(value) or value <= 0:
        return _DEFAULT_TIMEOUT
    return value


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
            timeout, or transport error); the endpoint responded with an
            HTTP error status (4xx/5xx); or the response body was malformed
            or missing the expected ``data[i].embedding`` shape. The message
            names both ``COHERENCE_EMBED_URL`` and ``COHERENCE_EMBED_MODEL``.
    """
    url = _embed_url()
    model = _embed_model()
    endpoint = f"{url.rstrip('/')}/embeddings"
    payload = {"model": model, "input": list(texts)}

    owns_client = client is None
    if client is None:
        client = httpx.Client(transport=transport, timeout=_embed_timeout())

    try:
        response = client.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]
    except (httpx.ConnectError, httpx.TimeoutException, httpx.TransportError) as exc:
        raise EmbedUnavailable(
            f"Embedding endpoint unreachable at {endpoint!r}: {exc}. "
            "Is an OpenAI-compatible embeddings server running? "
            f"Set COHERENCE_EMBED_URL (currently {url!r}) to the base URL and "
            f"COHERENCE_EMBED_MODEL (currently {model!r}) to a served model."
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise EmbedUnavailable(
            f"Embedding endpoint at {endpoint!r} returned an error status "
            f"({exc.response.status_code}). "
            f"Set COHERENCE_EMBED_URL (currently {url!r}) and "
            f"COHERENCE_EMBED_MODEL (currently {model!r}) to a reachable "
            "endpoint and a served model."
        ) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise EmbedUnavailable(
            f"Embedding endpoint at {endpoint!r} returned a malformed or "
            f"unexpected response body: {exc}. "
            f"Set COHERENCE_EMBED_URL (currently {url!r}) and "
            f"COHERENCE_EMBED_MODEL (currently {model!r}) to a reachable "
            "OpenAI-compatible /v1/embeddings endpoint."
        ) from exc
    finally:
        if owns_client:
            client.close()


__all__ = ["embed_texts", "DEFAULT_EMBED_URL", "DEFAULT_EMBED_MODEL"]
