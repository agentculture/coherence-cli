"""coherence.schema — the shared measurement envelope for coherence-cli's
five-domain restructure (quality, meaning, signal, investiture, assess).

Every measurement a NEW domain noun emits is a JSON dict with exactly five
top-level keys::

    {"domain": str,
     "score_type": str,
     "scores": {name: number, ...},
     "frame": dict | None,
     "diagnostics": [{"code": str, "message": str}, ...]}

* ``domain`` — which measurement domain produced this (``"quality"``,
  ``"meaning"``, ``"signal"``, ``"investiture"``, ...). Non-empty string.
* ``score_type`` — the falsifiability class of the numbers in ``scores``, e.g.
  ``"model_relative_anchor_defined_projection"`` (an embedding-anchor
  projection, gauge-dependent) or ``"rule_based_heuristic"`` (a deterministic
  text rule, no model dependency). Non-empty string.
* ``scores`` — an open map of named numeric scores. Any ``int``/``float``
  values; the key set is domain-defined and may grow without touching this
  module.
* ``frame`` — provenance of the measurement frame that produced ``scores``
  (e.g. embedding model, endpoint, anchor set, projection method). An
  **absent** frame is still represented explicitly — the key is always
  present — as either ``None`` (paired with a diagnostic explaining why, by
  convention) or a null-frame dict built by :func:`null_frame` that carries a
  machine-readable reason in-line. Never a missing key.
* ``diagnostics`` — a list of ``{"code": str, "message": str}`` dicts, the
  same always-available diagnostic shape already used by
  :mod:`coherence.meaning.diagnostics`. ``[]`` when there is nothing to flag.

This module is deliberately small and dependency-free (stdlib only): it is the
one shared contract that every new domain module builds its output through,
so it must not drag in numpy/httpx or any domain-specific code. See
``docs/envelope.md`` for the full field reference and the two-speed adoption
rule that governs how existing ``meaning`` outputs relate to this envelope.
"""

from __future__ import annotations

from typing import Any

# --- machine-readable error codes ------------------------------------------
#
# One code per distinguishable failure kind, so callers can branch on
# ``EnvelopeError.code`` instead of parsing the message string.
CODE_NOT_A_DICT = "envelope_not_a_dict"
CODE_MISSING_KEY = "envelope_missing_key"
CODE_INVALID_DOMAIN = "envelope_invalid_domain"
CODE_INVALID_SCORE_TYPE = "envelope_invalid_score_type"
CODE_INVALID_SCORES = "envelope_invalid_scores"
CODE_INVALID_SCORE_VALUE = "envelope_invalid_score_value"
CODE_INVALID_FRAME = "envelope_invalid_frame"
CODE_INVALID_DIAGNOSTICS = "envelope_invalid_diagnostics"
CODE_INVALID_DIAGNOSTIC_ENTRY = "envelope_invalid_diagnostic_entry"

# The exact five top-level keys every envelope must carry — ``frame`` is
# required as a *key* even when its value is ``None``.
_REQUIRED_KEYS: tuple[str, ...] = ("domain", "score_type", "scores", "frame", "diagnostics")
_DIAGNOSTIC_KEYS = {"code", "message"}


class EnvelopeError(ValueError):
    """Raised when a dict violates the shared measurement envelope contract.

    Carries a machine-readable :attr:`code` (one of the module-level
    ``CODE_*`` constants) alongside the human-readable message, so callers can
    branch on the failure kind rather than parsing strings.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def null_frame(reason: str, *, code: str = "frame_unavailable") -> dict[str, Any]:
    """Build the canonical null-frame dict for an explicitly absent frame.

    Some domains prefer to carry the "no provenance available" signal inline,
    as a dict, rather than setting ``envelope["frame"] = None``. Both forms
    are valid per the envelope contract (see ``docs/envelope.md``); this
    helper produces the dict form with a stable, machine-readable shape::

        {"available": False, "code": "frame_unavailable", "reason": reason}

    Args:
        reason: Human-readable explanation of why no frame is available
            (e.g. "embedding endpoint was unreachable at measurement time").
        code: Machine-readable reason code, defaults to ``"frame_unavailable"``.
    """
    return {"available": False, "code": code, "reason": reason}


def build_envelope(
    *,
    domain: str,
    score_type: str,
    scores: dict[str, Any],
    frame: dict[str, Any] | None,
    diagnostics: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Assemble the shared measurement envelope and validate it before returning.

    ``frame`` has no default — callers must always state explicitly whether a
    frame is present (a dict) or absent (``None``, or a :func:`null_frame`
    dict), matching the contract's "never a missing key, never an implicit
    absence" rule. ``diagnostics`` defaults to ``[]`` when omitted.

    Input mappings/lists are copied defensively (mutating the caller's
    ``scores``/``frame``/``diagnostics`` after this call does not affect the
    returned envelope).

    Raises:
        EnvelopeError: if the assembled envelope fails :func:`validate_envelope`.
    """
    envelope: dict[str, Any] = {
        "domain": domain,
        "score_type": score_type,
        "scores": dict(scores) if isinstance(scores, dict) else scores,
        "frame": dict(frame) if isinstance(frame, dict) else frame,
        "diagnostics": [dict(d) for d in diagnostics] if diagnostics is not None else [],
    }
    validate_envelope(envelope)
    return envelope


def validate_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Validate ``envelope`` against the shared measurement envelope contract.

    Returns ``envelope`` unchanged on success (so it can be chained, e.g.
    ``validate_envelope(build_envelope(...))``), and raises
    :class:`EnvelopeError` with a machine-readable ``code`` on the first
    violation found. Checks, in order:

    1. ``envelope`` itself is a dict.
    2. Every required key (``domain``, ``score_type``, ``scores``, ``frame``,
       ``diagnostics``) is *present* — ``frame`` may legitimately hold ``None``,
       but the key must never be missing.
    3. ``domain`` and ``score_type`` are non-empty strings.
    4. ``scores`` is a dict mapping str names to numeric (``int``/``float``,
       excluding ``bool``) values.
    5. ``frame`` is a dict or ``None``.
    6. ``diagnostics`` is a list of ``{"code": str, "message": str}`` dicts,
       each with non-empty string values and no extra keys.
    """
    if not isinstance(envelope, dict):
        raise EnvelopeError(
            CODE_NOT_A_DICT, f"envelope must be a dict, got {type(envelope).__name__}"
        )

    for key in _REQUIRED_KEYS:
        if key not in envelope:
            raise EnvelopeError(CODE_MISSING_KEY, f"envelope missing required key: {key!r}")

    domain = envelope["domain"]
    if not isinstance(domain, str) or not domain:
        raise EnvelopeError(CODE_INVALID_DOMAIN, "envelope['domain'] must be a non-empty str")

    score_type = envelope["score_type"]
    if not isinstance(score_type, str) or not score_type:
        raise EnvelopeError(
            CODE_INVALID_SCORE_TYPE, "envelope['score_type'] must be a non-empty str"
        )

    scores = envelope["scores"]
    if not isinstance(scores, dict):
        raise EnvelopeError(
            CODE_INVALID_SCORES,
            f"envelope['scores'] must be a dict, got {type(scores).__name__}",
        )
    for name, value in scores.items():
        if not isinstance(name, str):
            raise EnvelopeError(
                CODE_INVALID_SCORES,
                f"envelope['scores'] keys must be str, got {type(name).__name__}",
            )
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise EnvelopeError(
                CODE_INVALID_SCORE_VALUE,
                f"envelope['scores'][{name!r}] must be numeric, got {type(value).__name__}",
            )

    frame = envelope["frame"]
    if frame is not None and not isinstance(frame, dict):
        raise EnvelopeError(
            CODE_INVALID_FRAME,
            f"envelope['frame'] must be a dict or None, got {type(frame).__name__}",
        )

    diagnostics = envelope["diagnostics"]
    if not isinstance(diagnostics, list):
        raise EnvelopeError(
            CODE_INVALID_DIAGNOSTICS,
            f"envelope['diagnostics'] must be a list, got {type(diagnostics).__name__}",
        )
    for index, diagnostic in enumerate(diagnostics):
        if not isinstance(diagnostic, dict) or set(diagnostic) != _DIAGNOSTIC_KEYS:
            raise EnvelopeError(
                CODE_INVALID_DIAGNOSTIC_ENTRY,
                f"envelope['diagnostics'][{index}] must be exactly "
                "{'code': str, 'message': str}",
            )
        if not isinstance(diagnostic["code"], str) or not diagnostic["code"]:
            raise EnvelopeError(
                CODE_INVALID_DIAGNOSTIC_ENTRY,
                f"envelope['diagnostics'][{index}]['code'] must be a non-empty str",
            )
        if not isinstance(diagnostic["message"], str) or not diagnostic["message"]:
            raise EnvelopeError(
                CODE_INVALID_DIAGNOSTIC_ENTRY,
                f"envelope['diagnostics'][{index}]['message'] must be a non-empty str",
            )

    return envelope


__all__ = [
    "EnvelopeError",
    "build_envelope",
    "validate_envelope",
    "null_frame",
    "CODE_NOT_A_DICT",
    "CODE_MISSING_KEY",
    "CODE_INVALID_DOMAIN",
    "CODE_INVALID_SCORE_TYPE",
    "CODE_INVALID_SCORES",
    "CODE_INVALID_SCORE_VALUE",
    "CODE_INVALID_FRAME",
    "CODE_INVALID_DIAGNOSTICS",
    "CODE_INVALID_DIAGNOSTIC_ENTRY",
]
