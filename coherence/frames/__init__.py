"""coherence.frames — provenance of the semantic coordinate frame.

Per this repo's spec, embedding-derived scores are "model-relative,
anchor-defined semantic measurements" — never universal ones. The frame block
built by :mod:`coherence.frames.provenance` is the declared gauge: which
embedding model and endpoint produced the vectors, which anchor set and
axis/axes defined the projection, and what falsifiability class the resulting
score belongs to. Callers (meaning, investiture, signal, ...) attach it to the
``frame`` key of the shared measurement envelope (:mod:`coherence.schema`).

Public surface (re-exported from :mod:`coherence.frames.provenance` for
convenience):

* :func:`build_frame` — assemble a frame block, resolving
  ``embedding_model``/``embedding_endpoint`` from the runtime embed config
  (:mod:`coherence.meaning.embed`) at call time.
* :func:`null_frame` — re-exported from :mod:`coherence.schema`; the
  canonical explicit-absence representation for when no frame is available.
"""

from __future__ import annotations

from coherence.frames.provenance import build_frame, null_frame

__all__ = ["build_frame", "null_frame"]
