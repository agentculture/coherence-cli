"""Merge-contract tests for the plan-task-t5 refactor of :mod:`coherence.meaning.trend`.

Task t5 points ``meaning trend``'s difference math at the generic
:mod:`coherence.signal.trend` engine (``first_difference`` / ``second_difference``)
so ``meaning trend`` becomes a dimension-specific *wrapper* rather than a
reimplementation. **The externally observed output must not change at all** —
byte-identical JSON on the recorded fixtures is the merge contract.

This module proves that contract three ways, all fully OFFLINE:

1. **Pinned pre-refactor goldens.** The FULL ``trend`` result on the committed
   recorded-vector fixtures, and on a deterministic synthetic-embed series, is
   pinned as a golden JSON literal captured from the *pre-refactor* code. The
   machine-dependent absolute ``paths`` list is normalised to basenames (the
   only non-portable field); ``COHERENCE_EMBED_URL`` / ``COHERENCE_EMBED_MODEL``
   are pinned so the additive envelope ``frame`` block is deterministic. These
   literals were generated from the unrefactored module, run green against it,
   and byte-identity was reproduced by the refactored module on the capture
   machine. The committed assertion is a deep compare: structure, key sets,
   strings, and nulls exactly; floats at 1e-9 relative tolerance, because
   CPU/BLAS differences across machines shift the last ulp. A changed key,
   reason string, or any float beyond the last ulp still breaks it.

2. **Behavioural delegation-equivalence.** Every difference series in the
   output is shown to equal *exactly* what
   :func:`coherence.signal.trend.first_difference` /
   :func:`coherence.signal.trend.second_difference` compute on the same level
   and drift series. This holds before the refactor (meaning's private math was
   built with identical per-step semantics) and after (it literally calls those
   functions) — so it locks the output to the signal layer's math.

3. **Source-level delegation.** :func:`test_module_delegates_to_signal_trend`
   asserts the post-refactor structure directly: the module imports
   :mod:`coherence.signal.trend` and no longer defines a private
   ``_first_difference`` helper. Behavioural equivalence alone cannot prove the
   refactor *happened* (the old code satisfied it too, by construction), so this
   source check is what distinguishes "delegated" from "still reimplemented".
   Byte-identity (#1) proves the output is unchanged; equivalence (#2) proves it
   is the signal layer's math; this proves the code path is the signal layer's.
"""

from __future__ import annotations

import inspect
import json
import math
from pathlib import Path

import pytest

import coherence.meaning.trend as meaning_trend_mod
from coherence.meaning.trend import trend
from coherence.signal.trend import first_difference, second_difference

from ._meaning_recorded import load_recorded_embed_fn, recorded_vectors_present
from ._meaning_synthetic import synthetic_embed_fn

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "meaning"
_FILE_A = _FIXTURES / "auth_middleware.high.txt"
_FILE_B = _FIXTURES / "auth_middleware.low.txt"
_FILE_C = _FIXTURES / "payment_webhook.high.txt"

_SUBDIMENSIONS = ("consequence", "agency", "causality", "affordance", "future_constraint")

# Pinned so the additive envelope ``frame`` block is deterministic across runs
# and machines (it resolves embedding_model/endpoint from these at call time).
_GOLDEN_URL = "http://golden.test:1234/v1"
_GOLDEN_MODEL = "golden/embedding-model"

_recorded = pytest.mark.skipif(
    not recorded_vectors_present(),
    reason=(
        "recorded vectors absent — run scripts/refresh_meaning_vectors.py "
        "against a live embed gear"
    ),
)


def _normalize(result: dict) -> dict:
    """Return ``result`` with the machine-dependent absolute ``paths`` list
    replaced by basenames — the only non-portable field, so the rest can be
    pinned as an exact string literal."""
    out = dict(result)
    out["paths"] = [Path(p).name for p in result["paths"]]
    return out


def _assert_matches_golden(result: dict, golden: str) -> None:
    """Deep-compare ``result`` against a pinned golden JSON string.

    Structure, key sets, strings, nulls, and list lengths must match the
    golden EXACTLY; floats are compared with a tight relative tolerance
    (1e-9). Byte-identity was proven at refactor time on the capture
    machine (the golden was generated from the pre-refactor module and the
    refactored module reproduced it byte-for-byte); across machines, CPU /
    BLAS differences can shift the last ulp of a float, so CI compares
    numerically instead of textually.
    """

    def compare(a: object, b: object, path: str) -> None:
        if isinstance(a, dict) and isinstance(b, dict):
            assert a.keys() == b.keys(), f"{path}: key sets differ"
            for key in a:
                compare(a[key], b[key], f"{path}.{key}")
        elif isinstance(a, list) and isinstance(b, list):
            assert len(a) == len(b), f"{path}: list lengths differ"
            for i, (x, y) in enumerate(zip(a, b)):
                compare(x, y, f"{path}[{i}]")
        elif isinstance(a, float) or isinstance(b, float):
            assert isinstance(a, (int, float)) and isinstance(
                b, (int, float)
            ), f"{path}: type mismatch ({type(a).__name__} vs {type(b).__name__})"
            assert math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12), f"{path}: {a!r} != {b!r}"
        else:
            assert a == b, f"{path}: {a!r} != {b!r}"

    compare(_normalize(result), json.loads(golden), "$")


# --- the pinned pre-refactor goldens (captured verbatim from the unrefactored
#     module; exact structure + float-tolerant values are the merge contract) --

# Recorded-vector 3-point series (exercises first + second differences for every
# score signal and for drift).
_GOLDEN_RECORDED_3POINT = '{"domain": "meaning", "frame": {"anchor_set": "coherence-cli meaning anchors v1", "axes": ["meaning", "consequence", "agency", "causality", "affordance", "future_constraint"], "embedding_endpoint": "http://golden.test:1234/v1", "embedding_model": "golden/embedding-model", "projection_method": "mean(high) - mean(low), cosine projection", "score_type": "model_relative_anchor_defined_projection"}, "n": 3, "paths": ["auth_middleware.high.txt", "auth_middleware.low.txt", "payment_webhook.high.txt"], "per_step_drift": [0.3331370571013168, 0.749687952799134], "points": [{"meaning_score": 0.5580888283187754, "subdimensions": {"affordance": 0.4976016149741191, "agency": 0.5674962727487539, "causality": 0.4988241301431742, "consequence": 0.5635101999090149, "future_constraint": 0.5664468588305287}}, {"meaning_score": 0.4590491744662385, "subdimensions": {"affordance": 0.42328947487671, "agency": 0.5058056893114957, "causality": 0.44379452435992783, "consequence": 0.4456492058781504, "future_constraint": 0.5107760805713615}}, {"meaning_score": 0.6025028213831151, "subdimensions": {"affordance": 0.5033482071451851, "agency": 0.5165979735943044, "causality": 0.5095882124728057, "consequence": 0.5909230517421529, "future_constraint": 0.5212964047121155}}], "score_type": "model_relative_anchor_defined_projection", "second_difference_available": true, "signals": {"affordance": {"first": {"reason": null, "values": [-0.07431214009740911, 0.08005873226847515]}, "second": {"reason": null, "values": [0.15437087236588426]}}, "agency": {"first": {"reason": null, "values": [-0.061690583437258195, 0.01079228428280865]}, "second": {"reason": null, "values": [0.07248286772006685]}}, "causality": {"first": {"reason": null, "values": [-0.055029605783246394, 0.06579368811287789]}, "second": {"reason": null, "values": [0.12082329389612428]}}, "consequence": {"first": {"reason": null, "values": [-0.11786099403086447, 0.1452738458640025]}, "second": {"reason": null, "values": [0.26313483989486697]}}, "drift": {"first": {"reason": null, "values": [0.3331370571013168, 0.749687952799134]}, "second": {"reason": null, "values": [0.4165508956978172]}}, "future_constraint": {"first": {"reason": null, "values": [-0.05567077825916722, 0.01052032414075399]}, "second": {"reason": null, "values": [0.06619110239992121]}}, "meaning_score": {"first": {"reason": null, "values": [-0.09903965385253688, 0.14345364691687656]}, "second": {"reason": null, "values": [0.24249330076941344]}}}}'  # noqa: E501

# Synthetic-embed 3-point series (deterministic hash embedder; always runs).
_GOLDEN_SYNTH_3POINT = '{"domain": "meaning", "frame": {"anchor_set": "coherence-cli meaning anchors v1", "axes": ["meaning", "consequence", "agency", "causality", "affordance", "future_constraint"], "embedding_endpoint": "http://golden.test:1234/v1", "embedding_model": "golden/embedding-model", "projection_method": "mean(high) - mean(low), cosine projection", "score_type": "model_relative_anchor_defined_projection"}, "n": 3, "paths": ["auth_middleware.high.txt", "auth_middleware.low.txt", "payment_webhook.high.txt"], "per_step_drift": [0.4195613383199226, 0.33829773662041684], "points": [{"meaning_score": 0.6349675610422262, "subdimensions": {"affordance": 0.46593009541094543, "agency": 0.6750548388493914, "causality": 0.48032855335923585, "consequence": 0.4280779730864281, "future_constraint": 0.5814157362466944}}, {"meaning_score": 0.46665393407204325, "subdimensions": {"affordance": 0.5522871252658219, "agency": 0.6338631892801427, "causality": 0.483469537700665, "consequence": 0.46716287075537904, "future_constraint": 0.3802753491864813}}, {"meaning_score": 0.7008924423043891, "subdimensions": {"affordance": 0.4382020085263768, "agency": 0.5477980573963613, "causality": 0.6193840656474283, "consequence": 0.38472397633524286, "future_constraint": 0.5309137471679983}}], "score_type": "model_relative_anchor_defined_projection", "second_difference_available": true, "signals": {"affordance": {"first": {"reason": null, "values": [0.08635702985487648, -0.1140851167394451]}, "second": {"reason": null, "values": [-0.20044214659432158]}}, "agency": {"first": {"reason": null, "values": [-0.0411916495692487, -0.0860651318837814]}, "second": {"reason": null, "values": [-0.0448734823145327]}}, "causality": {"first": {"reason": null, "values": [0.0031409843414291205, 0.13591452794676334]}, "second": {"reason": null, "values": [0.13277354360533422]}}, "consequence": {"first": {"reason": null, "values": [0.03908489766895096, -0.08243889442013619]}, "second": {"reason": null, "values": [-0.12152379208908715]}}, "drift": {"first": {"reason": null, "values": [0.4195613383199226, 0.33829773662041684]}, "second": {"reason": null, "values": [-0.08126360169950575]}}, "future_constraint": {"first": {"reason": null, "values": [-0.2011403870602131, 0.150638397981517]}, "second": {"reason": null, "values": [0.3517787850417301]}}, "meaning_score": {"first": {"reason": null, "values": [-0.16831362697018293, 0.23423850823234582]}, "second": {"reason": null, "values": [0.40255213520252875]}}}}'  # noqa: E501

# Synthetic-embed 2-point series (exercises the n==2 second-unavailable branch:
# every ``second`` slot is null with the meaning-specific reason string).
_GOLDEN_SYNTH_2POINT = '{"domain": "meaning", "frame": {"anchor_set": "coherence-cli meaning anchors v1", "axes": ["meaning", "consequence", "agency", "causality", "affordance", "future_constraint"], "embedding_endpoint": "http://golden.test:1234/v1", "embedding_model": "golden/embedding-model", "projection_method": "mean(high) - mean(low), cosine projection", "score_type": "model_relative_anchor_defined_projection"}, "n": 2, "paths": ["auth_middleware.high.txt", "auth_middleware.low.txt"], "per_step_drift": [0.4195613383199226], "points": [{"meaning_score": 0.6349675610422262, "subdimensions": {"affordance": 0.46593009541094543, "agency": 0.6750548388493914, "causality": 0.48032855335923585, "consequence": 0.4280779730864281, "future_constraint": 0.5814157362466944}}, {"meaning_score": 0.46665393407204325, "subdimensions": {"affordance": 0.5522871252658219, "agency": 0.6338631892801427, "causality": 0.483469537700665, "consequence": 0.46716287075537904, "future_constraint": 0.3802753491864813}}], "score_type": "model_relative_anchor_defined_projection", "second_difference_available": false, "signals": {"affordance": {"first": {"reason": null, "values": [0.08635702985487648]}, "second": {"reason": "second difference (f\'\') needs at least 3 measurement points; got 2. A second difference is the first difference of the first-difference series, which is empty for a single step.", "values": null}}, "agency": {"first": {"reason": null, "values": [-0.0411916495692487]}, "second": {"reason": "second difference (f\'\') needs at least 3 measurement points; got 2. A second difference is the first difference of the first-difference series, which is empty for a single step.", "values": null}}, "causality": {"first": {"reason": null, "values": [0.0031409843414291205]}, "second": {"reason": "second difference (f\'\') needs at least 3 measurement points; got 2. A second difference is the first difference of the first-difference series, which is empty for a single step.", "values": null}}, "consequence": {"first": {"reason": null, "values": [0.03908489766895096]}, "second": {"reason": "second difference (f\'\') needs at least 3 measurement points; got 2. A second difference is the first difference of the first-difference series, which is empty for a single step.", "values": null}}, "drift": {"first": {"reason": null, "values": [0.4195613383199226]}, "second": {"reason": "second difference (f\'\') needs at least 3 measurement points; got 2. A second difference is the first difference of the first-difference series, which is empty for a single step.", "values": null}}, "future_constraint": {"first": {"reason": null, "values": [-0.2011403870602131]}, "second": {"reason": "second difference (f\'\') needs at least 3 measurement points; got 2. A second difference is the first difference of the first-difference series, which is empty for a single step.", "values": null}}, "meaning_score": {"first": {"reason": null, "values": [-0.16831362697018293]}, "second": {"reason": "second difference (f\'\') needs at least 3 measurement points; got 2. A second difference is the first difference of the first-difference series, which is empty for a single step.", "values": null}}}}'  # noqa: E501


def _set_golden_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COHERENCE_EMBED_URL", _GOLDEN_URL)
    monkeypatch.setenv("COHERENCE_EMBED_MODEL", _GOLDEN_MODEL)


# --- 1. byte-identity goldens ------------------------------------------------


@_recorded
def test_recorded_three_point_output_is_byte_identical(monkeypatch) -> None:
    _set_golden_env(monkeypatch)
    result = trend([_FILE_A, _FILE_B, _FILE_C], embed_fn=load_recorded_embed_fn())
    _assert_matches_golden(result, _GOLDEN_RECORDED_3POINT)


def test_synthetic_three_point_output_is_byte_identical(monkeypatch) -> None:
    _set_golden_env(monkeypatch)
    result = trend([_FILE_A, _FILE_B, _FILE_C], embed_fn=synthetic_embed_fn)
    _assert_matches_golden(result, _GOLDEN_SYNTH_3POINT)


def test_synthetic_two_point_output_is_byte_identical(monkeypatch) -> None:
    _set_golden_env(monkeypatch)
    result = trend([_FILE_A, _FILE_B], embed_fn=synthetic_embed_fn)
    _assert_matches_golden(result, _GOLDEN_SYNTH_2POINT)


# --- 2. behavioural delegation-equivalence to the signal layer ---------------


def _assert_series_are_signal_layer_math(result: dict) -> None:
    """Every difference series in ``result`` equals what
    :mod:`coherence.signal.trend`'s public functions compute on the same
    levels/drift — locking the meaning output to the signal layer's math."""
    n = result["n"]
    points = result["points"]

    def check_levels(name: str, levels: list[float]) -> None:
        slot = result["signals"][name]
        assert slot["first"]["values"] == first_difference(levels), name
        if n >= 3:
            assert slot["second"]["values"] == second_difference(levels), name
        else:
            assert slot["second"]["values"] is None, name

    check_levels("meaning_score", [p["meaning_score"] for p in points])
    for sub in _SUBDIMENSIONS:
        check_levels(sub, [p["subdimensions"][sub] for p in points])

    # Drift is already a per-step (first-order) series: it IS ``first``, and its
    # ``second`` is one more first_difference of it (never second_difference).
    drift = result["per_step_drift"]
    drift_slot = result["signals"]["drift"]
    assert drift_slot["first"]["values"] == drift
    if n >= 3:
        assert drift_slot["second"]["values"] == first_difference(drift)
    else:
        assert drift_slot["second"]["values"] is None


def test_synthetic_three_point_series_are_signal_layer_math(monkeypatch) -> None:
    _set_golden_env(monkeypatch)
    result = trend([_FILE_A, _FILE_B, _FILE_C], embed_fn=synthetic_embed_fn)
    _assert_series_are_signal_layer_math(result)


def test_synthetic_two_point_series_are_signal_layer_math(monkeypatch) -> None:
    _set_golden_env(monkeypatch)
    result = trend([_FILE_A, _FILE_B], embed_fn=synthetic_embed_fn)
    _assert_series_are_signal_layer_math(result)


@_recorded
def test_recorded_three_point_series_are_signal_layer_math(monkeypatch) -> None:
    _set_golden_env(monkeypatch)
    result = trend([_FILE_A, _FILE_B, _FILE_C], embed_fn=load_recorded_embed_fn())
    _assert_series_are_signal_layer_math(result)


# --- 3. source-level delegation (the refactor actually happened) -------------


def test_module_delegates_to_signal_trend() -> None:
    """The difference math moved out of ``coherence.meaning.trend`` and into the
    signal layer. Byte-identity (#1) proves the output did not change and
    equivalence (#2) proves it is the signal layer's math — but only this proves
    the *code path* is delegated rather than a still-present private copy."""
    # The private per-step difference helper is gone (it was the only difference
    # math in the module); its slot builder went with it.
    assert not hasattr(meaning_trend_mod, "_first_difference"), (
        "the private difference-math helper _first_difference must be removed — "
        "differencing now delegates to coherence.signal.trend"
    )
    assert not hasattr(meaning_trend_mod, "_slot")

    # The names the module now uses for differencing ARE the signal layer's
    # public functions (imported, not re-defined).
    assert meaning_trend_mod.first_difference is first_difference
    assert meaning_trend_mod.second_difference is second_difference

    # And the import is spelled out in source, so the dependency is explicit.
    source = inspect.getsource(meaning_trend_mod)
    assert "from coherence.signal.trend import" in source

    # The retained helpers stay (they are imported by tests/test_meaning_envelope_keys.py
    # and are labeling / distance / assembly, not first-or-second differencing).
    for retained in ("_derivatives_from_levels", "_derivatives_from_drift", "_cosine_distance"):
        assert hasattr(meaning_trend_mod, retained), retained
