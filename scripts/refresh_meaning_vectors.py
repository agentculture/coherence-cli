#!/usr/bin/env python3
"""Refresh the recorded embedding vectors used by the offline meaning tests.

The offline ordering test (``tests/test_meaning_ordering.py``) is the
falsifiability gate for the Meaning Gradient: it asserts that real embeddings
rank a rich artifact above a vague one. CI has no embedding gear, so the test
replays *recorded* vectors instead of hitting the network. This script produces
that recording — ``tests/fixtures/meaning/recorded_vectors.json``, a plain
``{text -> vector}`` map — by embedding, in one round-trip, the union of:

* every fixture file's full text under ``tests/fixtures/meaning/`` (each
  ``*.high.txt`` / ``*.low.txt`` pair and every ``series/*.txt`` version), and
* every anchor line across every dimension in
  :data:`coherence.meaning.axis.DIMENSIONS` (via
  :func:`coherence.meaning.axis.load_anchors`).

That union is exactly the set of strings ``coherence.meaning.score.measure``
embeds when scoring any fixture: the artifact text first, then every anchor
line for every dimension. Recording the union lets ``recorded_embed_fn`` serve
every ``score``/``compare``/``trend`` call by exact-string lookup, fully
offline.

WHEN TO RUN THIS
================
Run it **against a live embedding gear** (an OpenAI-compatible
``/v1/embeddings`` endpoint, e.g. eidetic's embed server) whenever either input
side changes:

* an anchor file under ``coherence/meaning/anchors/`` was edited/added, or
* a fixture under ``tests/fixtures/meaning/`` (a high/low pair or a series
  version) was edited/added.

Point ``COHERENCE_EMBED_URL`` (and ``COHERENCE_EMBED_MODEL``) at the gear, then::

    COHERENCE_EMBED_URL=http://localhost:8002/v1 \
        uv run --no-sync python scripts/refresh_meaning_vectors.py

Commit the regenerated ``recorded_vectors.json`` alongside the change that
triggered the refresh.

Why this matters (issue #6, risks r1/r2)
----------------------------------------
* **r1 — stale vectors.** If fixtures or anchors change but the recording is
  not refreshed, the offline test would replay vectors for text that no longer
  exists; ``recorded_embed_fn`` raises a loud, named error rather than silently
  passing on the wrong geometry. Re-running this script is the fix.
* **r2 — embedder drift.** The recorded geometry is only meaningful for the
  embedding model it was captured from. Regenerating deterministically from the
  live gear keeps the offline ordering gate faithful to the real model instead
  of freezing a geometry the production embedder no longer produces.
"""

from __future__ import annotations

import json
from pathlib import Path

from coherence.meaning import axis
from coherence.meaning.embed import embed_texts

# tests/fixtures/meaning/ lives two levels up from this script (repo/scripts/..).
_REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures" / "meaning"
RECORDED_PATH = FIXTURES_DIR / "recorded_vectors.json"


def _collect_texts() -> list[str]:
    """Return the sorted, de-duplicated union of fixture texts + anchor lines.

    Fixture texts are each file's *full* content (what ``score`` embeds as the
    artifact); anchor texts are the individual, stripped anchor lines (what
    ``measure`` embeds alongside the artifact). Sorting makes the batch order —
    and therefore the recorded file — deterministic.
    """
    texts: set[str] = set()

    # Every fixture artifact's full text (recursively: pairs + series/).
    for path in FIXTURES_DIR.rglob("*.txt"):
        texts.add(path.read_text(encoding="utf-8"))

    # Every anchor line for every dimension (stripped, as load_anchors returns).
    for dimension in axis.DIMENSIONS:
        high_lines, low_lines = axis.load_anchors(dimension)
        texts.update(high_lines)
        texts.update(low_lines)

    return sorted(texts)


def main() -> None:
    texts = _collect_texts()
    vectors = embed_texts(texts)
    if len(vectors) != len(texts):
        raise RuntimeError(
            f"embed_texts returned {len(vectors)} vectors for {len(texts)} texts "
            f"(expected {len(texts)}, got {len(vectors)}); refusing to write a "
            "truncated recorded_vectors.json"
        )
    recorded = {text: vector for text, vector in zip(texts, vectors)}

    RECORDED_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECORDED_PATH.write_text(
        json.dumps(recorded, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"recorded {len(recorded)} vectors -> {RECORDED_PATH}")


if __name__ == "__main__":
    main()
