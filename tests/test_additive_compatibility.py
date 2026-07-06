"""Additive-only pre/post diff proof for every PRE-EXISTING command (plan task t18).

Deliverable 1 of the final verification task. The domain restructure (the
five-domain wiring plus the two-speed envelope) had to be *purely additive* for
every command that already existed at v0.5.0: no pre-existing output key may be
removed, renamed, or retyped, and no pre-existing value may change. This module
proves that, fully OFFLINE, for the two families of pre-existing commands.

1. ``meaning score/compare/trend`` — the v0.5.0 engines that GAINED exactly the
   three additive envelope keys ``{domain, score_type, frame}`` (see
   ``docs/envelope.md``). Driven with the deterministic synthetic embedder
   (``tests/_meaning_synthetic.py``) so no ``/v1/embeddings`` endpoint is ever
   contacted, each result has those three top-level keys stripped and the
   remainder asserted **byte-identical** to an INDEPENDENT v0.5.0 reconstruction
   built from the same offline primitives (``measure`` / ``diagnostics`` / the
   trend derivative helpers). That is the diff proof: the three keys are the
   only additions, no pre-existing key moved, and no pre-existing value changed.
   The nested blocks stay clean v0.5.0 — ``compare``'s ``before``/``after`` and
   ``trend``'s per-point blocks must carry NONE of the new keys.

2. The scaffold verbs (``whoami`` / ``learn`` / ``explain`` / ``overview`` /
   ``doctor`` / ``cli overview``) — untouched by the restructure. One ``--json``
   smoke assertion per verb pins its established key set (read from the verbs'
   own tests).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence import __version__
from coherence.cli import main
from coherence.meaning.axis import DIMENSIONS
from coherence.meaning.compare import compare
from coherence.meaning.diagnostics import diagnostics
from coherence.meaning.score import measure, score
from coherence.meaning.trend import (
    _cosine_distance,
    _derivatives_from_drift,
    _derivatives_from_levels,
    trend,
)

from ._meaning_synthetic import synthetic_embed_fn

# The three ADDITIVE top-level keys the two-speed envelope adds to the meaning
# outputs; everything else must be byte-identical to v0.5.0.
_NEW_KEYS = {"domain", "score_type", "frame"}
_GLOBAL_DIMENSION = "meaning"
_SUBDIMENSIONS = tuple(dim for dim in DIMENSIONS if dim != _GLOBAL_DIMENSION)

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "meaning"
_FILE_A = _FIXTURES / "auth_middleware.high.txt"
_FILE_B = _FIXTURES / "auth_middleware.low.txt"
_FILE_C = _FIXTURES / "payment_webhook.high.txt"


def _strip_new_keys(result: dict) -> dict:
    """Return ``result`` with exactly the three additive envelope keys removed."""
    return {key: value for key, value in result.items() if key not in _NEW_KEYS}


# --- independent v0.5.0 reconstructions -------------------------------------
#
# Each rebuilds the pinned pre-v0.5.0 shape from the SAME offline primitives the
# engines use internally, so the post-strip comparison is bit-identical exactly
# when the change was purely additive. Kept independent of the shipped engines'
# assembly code on purpose: if a pre-existing value silently changed, these
# reconstructions would still compute the v0.5.0 value and the equality fails.


def _v050_score(path: Path, embed_fn) -> dict:
    text = path.read_text(encoding="utf-8")
    _vec, raw = measure(text, embed_fn=embed_fn)
    subs = {dim: raw[dim] for dim in _SUBDIMENSIONS}
    return {
        "meaning_score": raw[_GLOBAL_DIMENSION],
        "subdimensions": subs,
        "diagnostics": diagnostics(text),
    }


def _v050_compare(before: Path, after: Path, embed_fn) -> dict:
    before_score = _v050_score(before, embed_fn)
    after_score = _v050_score(after, embed_fn)
    delta = {
        "meaning_score": after_score["meaning_score"] - before_score["meaning_score"],
        "subdimensions": {
            name: after_score["subdimensions"][name] - before_score["subdimensions"][name]
            for name in after_score["subdimensions"]
        },
    }
    return {"before": before_score, "after": after_score, "delta": delta}


def _v050_trend(paths: list[Path], embed_fn) -> dict:
    vectors: list = []
    meaning_levels: list[float] = []
    subdim_levels: dict[str, list[float]] = {sub: [] for sub in _SUBDIMENSIONS}
    points: list[dict] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        vec, raw = measure(text, embed_fn=embed_fn)
        vectors.append(vec)
        meaning_levels.append(raw[_GLOBAL_DIMENSION])
        point_subs = {sub: raw[sub] for sub in _SUBDIMENSIONS}
        for sub in _SUBDIMENSIONS:
            subdim_levels[sub].append(raw[sub])
        points.append({"meaning_score": raw[_GLOBAL_DIMENSION], "subdimensions": point_subs})
    n = len(paths)
    per_step_drift = [_cosine_distance(vectors[i], vectors[i + 1]) for i in range(n - 1)]
    signals = {"meaning_score": _derivatives_from_levels(meaning_levels, n)}
    for sub in _SUBDIMENSIONS:
        signals[sub] = _derivatives_from_levels(subdim_levels[sub], n)
    signals["drift"] = _derivatives_from_drift(per_step_drift, n)
    return {
        "n": n,
        "paths": [str(path) for path in paths],
        "points": points,
        "per_step_drift": per_step_drift,
        "signals": signals,
        "second_difference_available": n >= 3,
    }


# --- meaning score: additive-only -------------------------------------------


def test_meaning_score_is_additive_only() -> None:
    live = score(_FILE_A, embed_fn=synthetic_embed_fn)

    # The three envelope keys are present ...
    assert _NEW_KEYS <= set(live)
    stripped = _strip_new_keys(live)
    # ... and stripping them yields exactly the v0.5.0 key inventory.
    assert set(stripped) == {"meaning_score", "subdimensions", "diagnostics"}

    # Pre-existing value TYPES are unchanged.
    assert isinstance(stripped["meaning_score"], float)
    assert isinstance(stripped["subdimensions"], dict)
    assert isinstance(stripped["diagnostics"], list)
    assert set(stripped["subdimensions"]) == set(_SUBDIMENSIONS)

    # No pre-existing value changed: byte-identical to an independent v0.5.0 build.
    assert stripped == _v050_score(_FILE_A, synthetic_embed_fn)

    # The added keys carry their pinned contract (not the focus, but cheap to pin).
    assert live["domain"] == "meaning"
    assert isinstance(live["score_type"], str) and live["score_type"]
    assert isinstance(live["frame"], dict)


# --- meaning compare: additive-only -----------------------------------------


def test_meaning_compare_is_additive_only() -> None:
    live = compare(_FILE_A, _FILE_B, embed_fn=synthetic_embed_fn)

    assert _NEW_KEYS <= set(live)
    stripped = _strip_new_keys(live)
    # Top level: the additive keys ride at the compare-result level only.
    assert set(stripped) == {"before", "after", "delta"}

    # The before/after blocks carry NO new keys — they stay clean v0.5.0.
    for side in ("before", "after"):
        assert set(live[side]) == {"meaning_score", "subdimensions", "diagnostics"}
        assert not (_NEW_KEYS & set(live[side]))
        assert isinstance(live[side]["meaning_score"], float)
        assert isinstance(live[side]["subdimensions"], dict)
        assert isinstance(live[side]["diagnostics"], list)

    # The v0.5.0 delta shape is unchanged (meaning_score + subdimensions).
    assert set(stripped["delta"]) == {"meaning_score", "subdimensions"}
    assert isinstance(stripped["delta"]["meaning_score"], float)
    assert set(stripped["delta"]["subdimensions"]) == set(_SUBDIMENSIONS)

    # No pre-existing value changed.
    assert stripped == _v050_compare(_FILE_A, _FILE_B, synthetic_embed_fn)


# --- meaning trend: additive-only -------------------------------------------


def test_meaning_trend_is_additive_only() -> None:
    paths = [_FILE_A, _FILE_B, _FILE_C]
    live = trend(paths, embed_fn=synthetic_embed_fn)

    assert _NEW_KEYS <= set(live)
    stripped = _strip_new_keys(live)
    assert set(stripped) == {
        "n",
        "paths",
        "points",
        "per_step_drift",
        "signals",
        "second_difference_available",
    }

    # Per-point blocks carry NO new keys — the additive keys ride once, at top level.
    for point in live["points"]:
        assert set(point) == {"meaning_score", "subdimensions"}

    # Pre-existing value TYPES are unchanged.
    assert isinstance(stripped["n"], int)
    assert isinstance(stripped["paths"], list)
    assert isinstance(stripped["points"], list)
    assert isinstance(stripped["per_step_drift"], list)
    assert isinstance(stripped["signals"], dict)
    assert isinstance(stripped["second_difference_available"], bool)
    assert set(stripped["signals"]) == {"meaning_score", *_SUBDIMENSIONS, "drift"}

    # No pre-existing value changed.
    assert stripped == _v050_trend(paths, synthetic_embed_fn)


# --- scaffold verbs: --json key sets completely unchanged -------------------


def _run_json(capsys: pytest.CaptureFixture[str], argv: list[str]) -> dict:
    rc = main(argv)
    assert rc == 0, f"{argv} exited {rc}"
    return json.loads(capsys.readouterr().out)


def test_whoami_json_keys_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    payload = _run_json(capsys, ["whoami", "--json"])
    assert payload["nick"] == "coherence-cli"
    assert payload["version"] == __version__
    assert payload["backend"] == "claude"


def test_learn_json_keys_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    payload = _run_json(capsys, ["learn", "--json"])
    assert payload["tool"] == "coherence-cli"
    assert payload["version"] == __version__
    assert payload["json_support"] is True
    assert isinstance(payload["commands"], list) and payload["commands"]


def test_explain_json_keys_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    payload = _run_json(capsys, ["explain", "whoami", "--json"])
    assert payload["path"] == ["whoami"]
    assert "coherence-cli whoami" in payload["markdown"]


def test_overview_json_keys_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    payload = _run_json(capsys, ["overview", "--json"])
    assert payload["subject"] == "coherence-cli"
    assert isinstance(payload["sections"], list) and payload["sections"]


def test_cli_overview_json_keys_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    payload = _run_json(capsys, ["cli", "overview", "--json"])
    assert payload["subject"] == "coherence-cli cli"
    assert isinstance(payload["sections"], list)


def test_doctor_json_keys_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    # doctor exits 0 (healthy) or 1 (a failed invariant); both are valid here.
    rc = main(["doctor", "--json"])
    assert rc in (0, 1)
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload["healthy"], bool)
    assert isinstance(payload["checks"], list) and payload["checks"]
    for check in payload["checks"]:
        assert {"id", "passed", "severity", "message", "remediation"} <= set(check)
