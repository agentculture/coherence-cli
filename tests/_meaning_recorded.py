"""Offline replay of recorded embedding vectors for the meaning ordering test.

The falsifiability gate (``tests/test_meaning_ordering.py``) needs *real*
embeddings to rank a rich artifact above a vague one, but CI has no embedding
gear. This helper loads the ``{text -> vector}`` map produced by
``scripts/refresh_meaning_vectors.py`` and returns an ``embed_fn`` that serves
each requested text by **exact-string lookup** — the same seam every engine
function accepts, so ``score``/``compare``/``trend`` run fully offline.

A missing text is a hard error, not a silent zero vector: if the fixtures or
anchors changed without re-recording, the lookup raises an ``AssertionError``
naming ``scripts/refresh_meaning_vectors.py`` so the fix is obvious.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

RECORDED_PATH = Path(__file__).resolve().parent / "fixtures" / "meaning" / "recorded_vectors.json"

EmbedFn = Callable[[list[str]], list[list[float]]]


def recorded_vectors_present() -> bool:
    """Return ``True`` when the recorded-vectors file exists on disk.

    The ordering test skips (rather than fails) when this is ``False`` — the
    recording is generated later against a live embed gear and is deliberately
    not committed.
    """
    return RECORDED_PATH.is_file()


def load_recorded_embed_fn() -> EmbedFn:
    """Return an offline ``embed_fn`` backed by the recorded-vectors file.

    The returned callable maps each input text to its recorded vector by exact
    string match, preserving input order. A text with no recording raises an
    ``AssertionError`` that names the refresh script, because it means the
    recording is stale relative to the current fixtures/anchors.

    Raises:
        FileNotFoundError: The recorded-vectors file is absent. Callers should
            gate on :func:`recorded_vectors_present` first.
    """
    if not recorded_vectors_present():
        raise FileNotFoundError(
            f"recorded vectors absent at {RECORDED_PATH}; run "
            "scripts/refresh_meaning_vectors.py against a live embed gear"
        )
    data = _recorded_vectors()

    def recorded_embed_fn(texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            if text not in data:
                raise AssertionError(
                    "no recorded vector for text "
                    f"{text[:80]!r}{'...' if len(text) > 80 else ''}; "
                    "the recorded vectors are stale — regenerate them with "
                    "scripts/refresh_meaning_vectors.py against a live embed gear"
                )
            vectors.append(data[text])
        return vectors

    return recorded_embed_fn


def _load_raw() -> dict:
    return json.loads(RECORDED_PATH.read_text(encoding="utf-8"))


def _is_wrapped(raw: dict) -> bool:
    """The wrapped format is ``{"metadata": {...}, "vectors": {...}}``; the
    legacy format is a flat ``{text -> vector}`` map (whose keys are artifact
    texts, never exactly this two-key envelope)."""
    return set(raw) == {"metadata", "vectors"}


def _recorded_vectors() -> dict[str, list[float]]:
    raw = _load_raw()
    return raw["vectors"] if _is_wrapped(raw) else raw


def load_recorded_metadata() -> dict | None:
    """Return the recording's provenance metadata, or ``None`` on legacy files.

    The metadata is the model tie-out (issue #10 / PR #14 review): it names the
    ``embedding_model``/``embedding_endpoint`` that produced the vectors, so a
    replay can be checked against the frame it claims instead of silently
    misstating provenance when the runtime env differs from the capture env.
    """
    raw = _load_raw()
    return raw["metadata"] if _is_wrapped(raw) else None
