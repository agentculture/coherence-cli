"""coherence.frames — provenance of the semantic coordinate frame.

Per this repo's spec, embedding-derived scores are "model-relative,
anchor-defined semantic measurements" — never universal ones. The frame block
built by :mod:`coherence.frames.provenance` is the declared gauge: which
embedding model and endpoint produced the vectors, which anchor set and
axis/axes defined the projection, and what falsifiability class the resulting
score belongs to. Callers (meaning, investiture, signal, ...) attach it to the
``frame`` key of the shared measurement envelope (:mod:`coherence.schema`).

``frames`` is also a real noun with its own engines, not just metadata carried
by other domains:

* :func:`inspect_measurement` (:mod:`coherence.frames.inspect`) — report the
  frame that produced a measurement JSON and whether its provenance is
  complete, partial, or absent.
* :func:`diff_frames` (:mod:`coherence.frames.diff`) — decide whether two
  measurements are frame-comparable (same gauge), naming any differing
  identity fields.
* :func:`check_series_frames` (:mod:`coherence.frames.compat`) — the
  mixed-frame guard, walking a loaded series's points for disagreeing frame
  identities; wired automatically into
  :func:`coherence.signal.schema.load_series`.

Public surface (re-exported for convenience):

* :func:`build_frame` — assemble a frame block, resolving
  ``embedding_model``/``embedding_endpoint`` from the runtime embed config
  (:mod:`coherence.meaning.embed`) at call time.
* :func:`null_frame` — re-exported from :mod:`coherence.schema`; the
  canonical explicit-absence representation for when no frame is available.
* :func:`inspect_measurement`, :func:`diff_frames`, :func:`check_series_frames`
  — the three engines above.
"""

from __future__ import annotations

from coherence.frames.compat import check_series_frames
from coherence.frames.diff import diff_frames
from coherence.frames.inspect import inspect_measurement
from coherence.frames.provenance import build_frame, null_frame

__all__ = [
    "build_frame",
    "null_frame",
    "inspect_measurement",
    "diff_frames",
    "check_series_frames",
]
