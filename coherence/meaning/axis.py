"""coherence.meaning.axis — anchor-axis construction and projection.

The Meaning Gradient scores an artifact by projecting its embedding onto a
*meaning axis* built from contrastive anchor examples: the global ``meaning``
axis plus five subdimensions (consequence, agency, causality, affordance,
future_constraint). This module is the pure numeric + fixture-loading core — it
never calls an embedding endpoint. Callers supply vectors (see the sibling
``embed`` module); the anchor *text* lives in ``anchors/<dimension>.high.txt``
and ``anchors/<dimension>.low.txt`` next to this file.

Two numeric primitives:

* ``build_axis(high_vecs, low_vecs)`` — ``mean(high) - mean(low)``: the
  direction in embedding space that points from low-meaning toward
  high-meaning examples.
* ``project(vec, axis)`` — cosine similarity of ``vec`` to ``axis`` rescaled
  from ``[-1, 1]`` to ``[0, 1]`` via ``(cos + 1) / 2``. Parallel -> 1.0,
  orthogonal -> 0.5, anti-parallel -> 0.0.

Both are deterministic: identical inputs yield identical outputs (plain numpy
mean/dot, no randomness).
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

# The global axis plus the 5 MVP subdimensions. ``meaning`` names the global
# axis; the rest are the subdimensions chosen in the spec/issue #4. Order is
# stable so downstream JSON keys stay in a documented order.
DIMENSIONS: tuple[str, ...] = (
    "meaning",
    "consequence",
    "agency",
    "causality",
    "affordance",
    "future_constraint",
)

# Anchor text files live alongside this module.
ANCHORS_DIR: Path = Path(__file__).resolve().parent / "anchors"

# Value returned by ``project`` when a direction is undefined — a zero-norm
# vector or a zero-norm axis has no direction, so cosine similarity is
# undefined. 0.5 is the neutral midpoint of the [0, 1] output range: neither
# high- nor low-meaning, the same value an orthogonal vector would score.
NEUTRAL_SCORE: float = 0.5


def build_axis(high_vecs: ArrayLike, low_vecs: ArrayLike) -> NDArray[np.float64]:
    """Return the meaning axis ``mean(high_vecs) - mean(low_vecs)``.

    ``high_vecs`` / ``low_vecs`` are each a 2-D array-like of shape
    ``(n_examples, dim)`` — one embedding row per anchor example. The returned
    axis is a 1-D array of length ``dim``.

    Raises ``ValueError`` if either set is empty or not 2-D.
    """
    high = np.asarray(high_vecs, dtype=np.float64)
    low = np.asarray(low_vecs, dtype=np.float64)
    if high.ndim != 2 or low.ndim != 2:
        raise ValueError(
            "high_vecs and low_vecs must each be 2-D (n_examples, dim); "
            f"got shapes {high.shape} and {low.shape}"
        )
    if high.shape[0] == 0 or low.shape[0] == 0:
        raise ValueError("high_vecs and low_vecs must each contain at least one vector")
    return high.mean(axis=0) - low.mean(axis=0)


def project(vec: ArrayLike, axis: ArrayLike) -> float:
    """Project ``vec`` onto ``axis`` and rescale cosine similarity to [0, 1].

    Returns ``(cos + 1) / 2`` where ``cos`` is the cosine similarity of ``vec``
    to ``axis``: parallel -> 1.0, orthogonal -> 0.5, anti-parallel -> 0.0.

    If either ``vec`` or ``axis`` has zero norm its direction is undefined, so
    the projection returns :data:`NEUTRAL_SCORE` (0.5) rather than dividing by
    zero.
    """
    v = np.asarray(vec, dtype=np.float64)
    a = np.asarray(axis, dtype=np.float64)
    v_norm = float(np.linalg.norm(v))
    a_norm = float(np.linalg.norm(a))
    if v_norm == 0.0 or a_norm == 0.0:
        return NEUTRAL_SCORE
    cos = float(np.dot(v, a) / (v_norm * a_norm))
    # Clamp tiny floating-point excursions outside [-1, 1] before rescaling.
    cos = max(-1.0, min(1.0, cos))
    return (cos + 1.0) / 2.0


def load_anchors(dimension: str) -> tuple[list[str], list[str]]:
    """Load the ``(high_lines, low_lines)`` anchor sets for ``dimension``.

    ``dimension`` must be one of :data:`DIMENSIONS` (``meaning`` for the global
    axis). Reads ``anchors/<dimension>.high.txt`` and ``.low.txt``, returning
    the stripped, non-empty lines of each as a list.

    Raises ``ValueError`` for an unknown dimension and ``FileNotFoundError`` if
    a declared dimension's anchor file is missing.
    """
    if dimension not in DIMENSIONS:
        raise ValueError(
            f"unknown dimension {dimension!r}; expected one of {', '.join(DIMENSIONS)}"
        )
    high = _read_lines(ANCHORS_DIR / f"{dimension}.high.txt")
    low = _read_lines(ANCHORS_DIR / f"{dimension}.low.txt")
    return high, low


def _read_lines(path: Path) -> list[str]:
    """Return the stripped, non-empty lines of ``path``."""
    if not path.is_file():
        raise FileNotFoundError(f"anchor file missing: {path}")
    lines: Sequence[str] = path.read_text(encoding="utf-8").splitlines()
    return [stripped for stripped in (ln.strip() for ln in lines) if stripped]


__all__ = [
    "DIMENSIONS",
    "ANCHORS_DIR",
    "NEUTRAL_SCORE",
    "build_axis",
    "project",
    "load_anchors",
]
