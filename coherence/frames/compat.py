"""coherence.frames.compat — the mixed-frame guard.

A :class:`~coherence.signal.schema.Series` can carry points measured under
different semantic coordinate frames (a trend built by appending a later run's
scores to an earlier one, a hand-assembled series mixing two embedding
endpoints, ...). Comparing across those points — a first difference, a
correlation, a forecast — silently mixes gauges: the resulting number looks
like a normal measurement but means nothing, because it subtracts (or
correlates, or extrapolates) values from two different instruments. This
module is the guard against that: :func:`check_series_frames` walks a loaded
series's points and turns a silent gauge mismatch into a visible diagnostic.

This is wired directly into :func:`coherence.signal.schema.load_series` (see
that module's one-line hook at the end of the function) so the guard fires at
load time for every series, not only when a caller remembers to invoke it —
"never a silent number downstream" is the acceptance bar task t14 sets for
this module.

Same "identity" as :mod:`coherence.frames.diff`
------------------------------------------------
"Mixed" here means the same thing :mod:`coherence.frames.diff` means by "not
comparable": a different value in one of :data:`coherence.frames.diff.IDENTITY_FIELDS`
(``embedding_model``, ``embedding_endpoint``, ``anchor_set``,
``projection_method``) — the actual gauge. This module reuses
:func:`coherence.frames.diff.frame_identity` rather than re-deriving that
notion, so the two engines can never quietly drift apart on what "the same
frame" means. An ``axis``/``axes`` or ``score_type`` difference alone does
NOT trigger the mixed-frames warning here, matching ``diff``'s "soft
difference" treatment of those fields.

Three rules
-----------
* **All points' frames absent -> NOT mixed, no warning.** A series with no
  per-point provenance at all carries no contradiction to flag; missing
  provenance is :mod:`coherence.frames.inspect`'s job to report, not this
  guard's. Silence here is correct, not an oversight.
* **Some points framed, some not -> ``partially_framed`` warning.** A
  comparison across these points mixes a real gauge with an unknown one.
* **Two or more distinct non-null identities among the framed points ->
  ``mixed_frames`` warning.** The clearest case: two genuinely different
  gauges are both present in the same series.

The two warnings are independent and both may fire on the same series (e.g.
two distinct frames plus some unframed points).

Fully offline: no network, no embeddings call — this module only inspects
already-normalized :class:`~coherence.signal.schema.SeriesPoint` objects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from coherence.frames.diff import frame_identity

if TYPE_CHECKING:  # pragma: no cover - import cycle guard, type-checking only
    from coherence.signal.schema import Series

# --- machine-readable diagnostic codes --------------------------------------
CODE_PARTIALLY_FRAMED = "partially_framed"
CODE_MIXED_FRAMES = "mixed_frames"


def _diag(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def check_series_frames(series: "Series") -> list[dict[str, str]]:
    """Walk ``series.points`` and return mixed/partially-framed warnings.

    Never raises and never mutates ``series`` — callers (including
    :func:`coherence.signal.schema.load_series`) append the returned list onto
    their own diagnostics.

    Args:
        series: A loaded :class:`~coherence.signal.schema.Series` (or any
            object exposing a ``.points`` list of objects with a ``.frame``
            attribute — duck-typed so this module never needs to import
            :mod:`coherence.signal.schema` at runtime).

    Returns:
        A list of ``{"code", "message"}`` diagnostics: ``[]`` when every
        point's frame is absent (nothing to compare) or every framed point
        shares one identity; up to two entries — :data:`CODE_PARTIALLY_FRAMED`
        and/or :data:`CODE_MIXED_FRAMES` — otherwise.
    """
    identities: list[tuple[Any, ...] | None] = [frame_identity(p.frame) for p in series.points]
    total = len(identities)
    present = [identity for identity in identities if identity is not None]

    if not present:
        # All absent (including the empty-series case) -> nothing to flag;
        # missing provenance is frames.inspect's job, not this guard's.
        return []

    diagnostics: list[dict[str, str]] = []
    absent_count = total - len(present)
    if absent_count > 0:
        diagnostics.append(
            _diag(
                CODE_PARTIALLY_FRAMED,
                f"{absent_count} of {total} series point(s) carry no frame provenance "
                f"while {len(present)} do; comparisons across these points may mix a "
                "known gauge with an unknown one",
            )
        )

    distinct = set(present)
    if len(distinct) > 1:
        diagnostics.append(
            _diag(
                CODE_MIXED_FRAMES,
                f"series points carry {len(distinct)} distinct frame identities "
                "(embedding_model/embedding_endpoint/anchor_set/projection_method); "
                "comparing across them mixes gauges -- see 'coherence frames diff'",
            )
        )

    return diagnostics


__all__ = ["check_series_frames", "CODE_PARTIALLY_FRAMED", "CODE_MIXED_FRAMES"]
