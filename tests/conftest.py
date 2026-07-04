"""Shared pytest fixtures — chiefly the global zero-network embedding guard.

Every meaning test is required to run with **no network access**: unit tests
inject their own ``embed_fn``, the schema/CLI tests inject a synthetic one, and
the ordering test replays recorded vectors. To make an *accidental* real
embedding call fail loudly instead of silently reaching for
``COHERENCE_EMBED_URL``, this autouse fixture patches the network embedder
:func:`coherence.meaning.embed.embed_texts` to raise.

Why this does not break the existing suite:

* Tests that inject their own ``embed_fn`` never touch the real embedder.
* ``tests/test_meaning_embed.py`` binds ``embed_texts`` into its *own* module
  namespace at import time (``from coherence.meaning.embed import embed_texts``)
  and drives it through an injected ``httpx.MockTransport``; patching the
  *source* module attribute here does not rebind that already-imported name, so
  those tests keep exercising the real client offline.
* The CLI ``--json`` tests can't rely on the engine's default ``embed_fn``
  (a keyword default binds to the real function object at def-time, so patching
  this module attribute is inert for it — see ``test_meaning_schema.py``); they
  inject the synthetic embedder into the real engine explicitly, so they never
  reach this guard either.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_network_embed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if any test reaches the real network embedder.

    Patched at the source-module attribute
    ``coherence.meaning.embed.embed_texts``; monkeypatch reverts it after each
    test. Tests must inject a synthetic or recorded ``embed_fn`` instead.
    """

    def _blocked(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError(
            "network disabled in tests: coherence.meaning.embed.embed_texts was "
            "called with the network path. Inject a synthetic or recorded "
            "embed_fn instead (see tests/conftest.py)."
        )

    monkeypatch.setattr("coherence.meaning.embed.embed_texts", _blocked)
