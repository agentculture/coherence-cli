"""coherence.meaning — embedding and semantic-analysis support."""

from __future__ import annotations


class EmbedUnavailable(Exception):
    """Raised when the embedding endpoint is unreachable."""

    pass


__all__ = ["EmbedUnavailable"]
