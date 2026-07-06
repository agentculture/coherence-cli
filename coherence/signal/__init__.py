"""coherence.signal — the source-agnostic series analysis layer.

The ``signal`` domain is deliberately blind to *what* produced a series. It
consumes an ordered list of measurement points, each carrying a bag of
arbitrarily named numeric values, and offers a family of engines over that one
shape — trend (first/second differences), pattern (motif detection), resonance
(pairwise alignment), forecast (naive extrapolation) — so every current and
future measurement dimension gets trajectory analysis without reimplementation.

:mod:`coherence.signal.schema` defines that shared series input schema (the
documented contract every downstream engine consumes) and a robust loader. See
``docs/signal-series.md`` for the field reference.
"""

from __future__ import annotations

__all__: list[str] = []
