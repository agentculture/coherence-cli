"""A synthetic, deterministic ``embed_fn`` for the offline schema tests.

The schema/CLI/experiment tests only assert *shape and wiring* — the exact
top-level keys, the five named subdimensions, unit-range floats, and that
``compare`` and ``trend`` agree with each other. None of that needs real
embedding geometry, so these tests avoid the recorded-vectors file entirely and
use this hash-derived embedder instead: it maps each text to a fixed-dimension,
non-zero vector, deterministically and offline. Distinct texts get distinct
vectors and any non-empty text yields a non-zero vector, so projections stay
well-defined.
"""

from __future__ import annotations

import hashlib

_DIM = 16


def synthetic_embed_fn(texts: list[str]) -> list[list[float]]:
    """Return one deterministic pseudo-embedding per input, order preserved.

    Each vector is derived from the SHA-256 digest of the text, with byte
    values scaled into ``[0, 1]`` — reproducible across runs and processes (so
    it is safe under ``pytest -n auto``) and non-zero for any non-empty text.
    """
    vectors: list[list[float]] = []
    for text in texts:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vectors.append([digest[i % len(digest)] / 255.0 for i in range(_DIM)])
    return vectors
