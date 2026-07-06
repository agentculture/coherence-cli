"""coherence.meaning.trend — f'/f'' derivatives over a measurement-point series.

The trend engine is the step above the two-point :mod:`coherence.meaning.compare`
engine: given an *ordered* series of artifact versions, it reports how meaning
*moves* across the whole series — its per-step velocity (first difference, f')
and acceleration (second difference, f''). No history store, no time axis: just
discrete differences between consecutive measurement points.

Design constraints (mirroring ``score`` and ``compare``):

* **Reuse, don't reimplement.** Each artifact is scored through
  :func:`coherence.meaning.score.measure` — the one-embed helper that returns
  both the artifact's embedding vector *and* its raw per-dimension scores from a
  single ``embed_fn`` round-trip. The same ``embed_fn`` injection seam is
  threaded through so tests drive it fully offline. Each artifact is embedded
  **exactly once** (one ``measure`` call per point).
* **Per-step and unitless.** Differences are plain ``s[i+1] - s[i]`` between
  consecutive points — no division by any time delta. A "step" is one gap
  between adjacent points in the series.
* **Two signal families.** (a) *Score derivatives* — f'/f'' of the global
  ``meaning_score`` and of each subdimension. (b) *Embedding drift* — the cosine
  distance ``1 - cos(v_i, v_{i+1})`` between consecutive artifact vectors, which
  is itself the artifact's first-order velocity through embedding space, plus
  its own second difference (acceleration).
* **An open subdimension registry.** Subdimensions are read from the scores
  :func:`~coherence.meaning.score.measure` actually returns (iterating
  :data:`coherence.meaning.axis.DIMENSIONS`), so registering a sixth
  subdimension flows through here with no change.

Index alignment
---------------
For ``n`` measurement points every signal's first difference has length
``n - 1`` and its second difference has length ``n - 2``. This holds uniformly
for the score signals *and* for drift, because the per-step drift series is
already a first-order (velocity) quantity: it occupies the ``first`` slot
directly (length ``n - 1``), and differencing it once yields the ``second`` slot
(length ``n - 2``). The score signals are per-*point* levels (length ``n``), so
they must be differenced once to reach ``first`` and twice to reach ``second``.

At ``n == 2`` there are not enough points for a second difference, so every
``second`` slot is marked unavailable — ``values`` is ``null`` with a
``reason`` string — rather than raising.

JSON output shape
-----------------
:func:`trend` returns a plain, JSON-serialisable ``dict``::

    {
      "n": <int>,                        # number of measurement points (>= 2)
      "paths": ["a.md", "b.md", ...],    # the input paths, as strings, in order

      # Raw per-POINT values (length n) so the score series are interpretable.
      "points": [
        {"meaning_score": <float>,
         "subdimensions": {"consequence": <float>, "agency": <float>,
                           "causality": <float>, "affordance": <float>,
                           "future_constraint": <float>}},
        ...                              # one entry per point, in series order
      ],

      # Raw per-STEP embedding drift (length n-1): cosine distance
      # 1 - cos(v_i, v_{i+1}) between consecutive artifact vectors. This is the
      # same series as signals.drift.first.values, surfaced here for
      # interpretability alongside the raw point levels.
      "per_step_drift": [<float>, ...],

      # Every signal shares one schema: a "first" and a "second" derivative
      # slot, each {"values": <list|null>, "reason": <str|null>}.
      #   first.values  : length n-1, always present (reason null).
      #   second.values : length n-2 when n>=3 (reason null);
      #                    null with a reason string when n==2.
      "signals": {
        "meaning_score":     {"first": {"values": [...], "reason": null},
                              "second": {"values": [...]|null, "reason": <str|null>}},
        "consequence":       {"first": {...}, "second": {...}},
        "agency":            {"first": {...}, "second": {...}},
        "causality":         {"first": {...}, "second": {...}},
        "affordance":        {"first": {...}, "second": {...}},
        "future_constraint": {"first": {...}, "second": {...}},
        # Embedding-drift family. first == the per-step drift itself (velocity
        # through embedding space); second == its difference (acceleration).
        "drift":             {"first": {...}, "second": {...}}
      },

      # Convenience flag: True when n>=3 (second differences populated),
      # False when n==2 (every second.values is null).
      "second_difference_available": <bool>,

      # Additive two-speed envelope keys (the keys above keep their pinned
      # v0.5.0 shape byte-identical). One shared frame block for the whole
      # series — see docs/envelope.md.
      "domain": "meaning",
      "score_type": "model_relative_anchor_defined_projection",
      "frame": {"embedding_model": ..., "embedding_endpoint": ...,
                "anchor_set": ..., "projection_method": ...,
                "score_type": ..., "axes": [...]}
    }

Agreement with ``compare``
--------------------------
On exactly two points, ``trend([before, after])``'s first differences are
*identical* to :func:`coherence.meaning.compare.compare`'s ``delta``: both
reduce to ``score(after) - score(before)`` for ``meaning_score`` and each
subdimension, computed through the same ``measure`` machinery with the same
injected ``embed_fn``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
from numpy.typing import ArrayLike

from coherence.meaning import axis as axis_mod
from coherence.meaning.embed import embed_texts
from coherence.meaning.score import DOMAIN, SCORE_TYPE, EmbedFn, meaning_frame, measure

# The global-axis dimension name; it maps to the top-level ``meaning_score``
# rather than into the per-point ``subdimensions`` map (mirrors ``score``).
_GLOBAL_DIMENSION = "meaning"

# A vector whose L2 norm is at or below this is treated as effectively zero (its
# direction is undefined). A small epsilon guards near-zero vectors too and
# avoids fragile floating-point equality against ``0.0``.
_ZERO_NORM_EPS = 1e-12


def _second_unavailable_reason(n: int) -> str:
    """Return the reason string used when a second difference cannot be formed."""
    return (
        f"second difference (f'') needs at least 3 measurement points; got {n}. "
        "A second difference is the first difference of the first-difference "
        "series, which is empty for a single step."
    )


def _first_difference(series: Sequence[float]) -> list[float]:
    """Return the discrete first difference ``[s[i+1] - s[i] for i]``.

    A per-step, unitless difference: the result is one shorter than ``series``
    (empty when ``series`` has fewer than two elements).
    """
    return [series[i + 1] - series[i] for i in range(len(series) - 1)]


def _cosine_distance(u: ArrayLike, v: ArrayLike) -> float:
    """Return the cosine distance ``1 - cos(u, v)`` between two vectors.

    Ranges from ``0.0`` (identical direction) through ``1.0`` (orthogonal) to
    ``2.0`` (opposite). If either vector has zero norm its direction is
    undefined, so the distance is reported as ``0.0`` (mirrors the zero-norm
    guard in :func:`coherence.meaning.axis.project`).
    """
    a = np.asarray(u, dtype=np.float64)
    b = np.asarray(v, dtype=np.float64)
    a_norm = float(np.linalg.norm(a))
    b_norm = float(np.linalg.norm(b))
    if a_norm <= _ZERO_NORM_EPS or b_norm <= _ZERO_NORM_EPS:
        return 0.0
    cos = float(np.dot(a, b) / (a_norm * b_norm))
    # Clamp tiny floating-point excursions outside [-1, 1] before the distance.
    cos = max(-1.0, min(1.0, cos))
    return 1.0 - cos


def _derivatives_from_levels(levels: Sequence[float], n: int) -> dict:
    """Build the ``{first, second}`` slot for a per-*point* level series.

    ``levels`` has length ``n``; ``first`` is its difference (length ``n-1``)
    and ``second`` is the difference of ``first`` (length ``n-2``, or null with
    a reason when ``n < 3``).
    """
    first = _first_difference(levels)
    return _slot(first, n)


def _derivatives_from_drift(drift: Sequence[float], n: int) -> dict:
    """Build the ``{first, second}`` slot for the per-*step* drift series.

    The drift series (length ``n-1``) is already the first-order velocity
    through embedding space, so it *is* ``first``; ``second`` is its difference
    (length ``n-2``, or null with a reason when ``n < 3``).
    """
    return _slot(list(drift), n)


def _slot(first: list[float], n: int) -> dict:
    """Wrap a first-difference series and derive its second difference.

    ``first`` (length ``n-1``) goes into the ``first`` slot verbatim; its own
    first difference becomes the ``second`` slot (length ``n-2``). When ``n <
    3`` the second difference is empty, so it is reported as ``null`` with a
    ``reason`` rather than an empty list.
    """
    if n >= 3:
        second = {"values": _first_difference(first), "reason": None}
    else:
        second = {"values": None, "reason": _second_unavailable_reason(n)}
    return {"first": {"values": first, "reason": None}, "second": second}


def trend(paths: Sequence[str | Path], *, embed_fn: EmbedFn = embed_texts) -> dict:
    """Compute per-step f'/f'' trends across an ordered series of artifacts.

    Reads each path's text once and calls
    :func:`coherence.meaning.score.measure` once per point — so each artifact is
    embedded exactly once — collecting per-point score vectors and raw scores.
    From those it emits, for the global ``meaning_score``, each subdimension, and
    the embedding drift, a per-step first difference (f', velocity) and, when
    there are at least three points, a second difference (f'', acceleration).

    See the module docstring for the exact JSON output shape.

    Args:
        paths: An ordered sequence of at least two artifact file paths. Order is
            significant — differences are taken between consecutive entries.
        embed_fn: Batch embedder, injectable for offline tests. Threaded
            unchanged into :func:`~coherence.meaning.score.measure` for every
            point. Defaults to the real HTTP
            :func:`~coherence.meaning.embed.embed_texts`.

    Returns:
        A JSON-serialisable ``dict`` (see module docstring).

    Raises:
        ValueError: Fewer than two paths were supplied (no step to difference).
        EmbedUnavailable: Propagated from ``embed_fn`` when the endpoint is down.
    """
    paths = list(paths)
    n = len(paths)
    if n < 2:
        raise ValueError(f"trend needs at least 2 measurement points to form a step; got {n}")

    # Subdimensions are whatever the score engine returns (open registry): every
    # DIMENSIONS entry except the global "meaning" axis, in registry order.
    subdimension_names = tuple(dim for dim in axis_mod.DIMENSIONS if dim != _GLOBAL_DIMENSION)

    # One embed per point (measure does a single embed_fn round-trip); collect
    # each point's vector (for drift) and raw scores (for the derivatives).
    vectors: list[np.ndarray] = []
    meaning_levels: list[float] = []
    subdim_levels: dict[str, list[float]] = {sub: [] for sub in subdimension_names}
    points: list[dict] = []
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        artifact_vec, raw_scores = measure(text, embed_fn=embed_fn)
        vectors.append(artifact_vec)
        meaning_levels.append(raw_scores[_GLOBAL_DIMENSION])
        point_subs: dict[str, float] = {}
        for sub in subdimension_names:
            subdim_levels[sub].append(raw_scores[sub])
            point_subs[sub] = raw_scores[sub]
        points.append({"meaning_score": raw_scores[_GLOBAL_DIMENSION], "subdimensions": point_subs})

    # Per-step embedding drift: cosine distance between consecutive vectors.
    per_step_drift = [_cosine_distance(vectors[i], vectors[i + 1]) for i in range(n - 1)]

    # Score-derivative signals + the drift family, all sharing one slot schema.
    signals: dict[str, dict] = {"meaning_score": _derivatives_from_levels(meaning_levels, n)}
    for sub in subdimension_names:
        signals[sub] = _derivatives_from_levels(subdim_levels[sub], n)
    signals["drift"] = _derivatives_from_drift(per_step_drift, n)

    return {
        "n": n,
        "paths": [str(path) for path in paths],
        "points": points,
        "per_step_drift": per_step_drift,
        "signals": signals,
        "second_difference_available": n >= 3,
        # Additive two-speed envelope keys (the pre-existing keys above stay
        # byte-identical; see ``docs/envelope.md``). One top-level frame block
        # for the whole series — every point was measured under the same runtime
        # embed config, so a single shared frame describes them all.
        "domain": DOMAIN,
        "score_type": SCORE_TYPE,
        "frame": meaning_frame(),
    }


__all__ = ["trend"]
