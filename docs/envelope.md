# The shared measurement envelope

`coherence.schema` (`coherence/schema.py`) defines the common JSON shape for
every measurement domain in coherence-cli's five-domain restructure: quality,
meaning, signal, and investiture, plus the `assess` multi-domain report. It is
stdlib-only, dependency-free, and imports nothing domain-specific — every
domain module builds its output *through* this one shared contract instead of
inventing its own JSON shape.

## The five fields

A conformant envelope is a JSON object with exactly these top-level keys:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `domain` | `str` | yes, non-empty | Which measurement domain produced this envelope — e.g. `"quality"`, `"meaning"`, `"signal"`, `"investiture"`. |
| `score_type` | `str` | yes, non-empty | The falsifiability class of the numbers in `scores` — e.g. `"model_relative_anchor_defined_projection"` (an embedding-anchor projection: gauge-dependent, only comparable within the same frame) or `"rule_based_heuristic"` (a deterministic text rule: no model dependency, comparable across runs). |
| `scores` | `dict` | yes | An open map of named numeric (`int`/`float`) scores. The key set is domain-defined and can grow without touching `coherence/schema.py`. |
| `frame` | `dict` or `None` | yes, **key always present** | Provenance of the measurement frame that produced `scores` — e.g. embedding model, endpoint, anchor set, projection method for a model-relative score; `None` (or absent-info) for a rule-based one with nothing to attribute. |
| `diagnostics` | `list[dict]` | yes | A list of `{"code": str, "message": str}` entries — the same always-available diagnostic shape already used by `coherence.meaning.diagnostics`. `[]` when there is nothing to flag. |

### Example — a model-relative score with a full frame

```json
{
  "domain": "meaning",
  "score_type": "model_relative_anchor_defined_projection",
  "scores": {"meaning_score": 0.62},
  "frame": {
    "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
    "embedding_endpoint": "http://localhost:8001/v1",
    "anchor_set": "meaning-v1",
    "projection_method": "contrastive_axis"
  },
  "diagnostics": []
}
```

### Example — a rule-based score with no frame to attribute

```json
{
  "domain": "quality",
  "score_type": "rule_based_heuristic",
  "scores": {"freshness": 0.8, "provenance": 0.5, "fidelity": 0.4},
  "frame": null,
  "diagnostics": [
    {"code": "no_dateable_statement", "message": "no date or age signal found in the artifact"}
  ]
}
```

## Frame absence is explicit, never a missing key

Some measurements have no frame to report — a purely rule-based heuristic has
no embedding model to attribute, or an upstream input simply didn't carry
provenance forward. The envelope contract still requires the `frame` **key**
to be present in every case; only its *value* changes. Two equally valid ways
to represent "no frame":

1. **`frame: null`, paired with a diagnostic.** Set `envelope["frame"]` to
   `None` and add a `{"code": ..., "message": ...}` entry to `diagnostics`
   explaining why (e.g. `"frame_unavailable"` / `"input carried no
   provenance"`). This is the default convention for "genuinely nothing to
   report."
2. **A null-frame dict with a machine-readable reason**, built by
   `coherence.schema.null_frame(reason, *, code="frame_unavailable")`, which
   returns `{"available": False, "code": ..., "reason": ...}`. Some callers
   prefer to carry the absence signal inline in the `frame` value itself
   (still a `dict`, so it satisfies "`frame` is a dict or `None`") rather than
   relying on a separate diagnostics entry.

What is never valid: omitting the `frame` key from the dict entirely. A
missing key is ambiguous (forgotten vs. deliberately absent); an explicit
`null` or null-frame dict is not. `coherence.schema.validate_envelope` rejects
a dict lacking any of the five required keys — including `frame` — with a
dedicated `EnvelopeError` (see below), specifically so "forgot to attach the
frame" fails loudly instead of silently shipping malformed JSON.

## `coherence.schema` API

```python
from coherence.schema import build_envelope, validate_envelope, null_frame, EnvelopeError

envelope = build_envelope(
    domain="quality",
    score_type="rule_based_heuristic",
    scores={"freshness": 0.8},
    frame=None,
    diagnostics=[{"code": "no_dateable_statement", "message": "..."}],
)
validate_envelope(envelope) == envelope  # round-trips unchanged
```

* **`build_envelope(*, domain, score_type, scores, frame, diagnostics=None)`**
  — assembles the five-key dict (defensive copies of `scores`/`frame`/
  `diagnostics`, `diagnostics` defaults to `[]`) and validates it before
  returning. `frame` has no default: callers must always state explicitly
  whether a frame is present (a `dict`) or absent (`None` or a `null_frame()`
  dict) — there is no silent "I forgot" path.
* **`validate_envelope(envelope)`** — checks a raw dict against the contract
  (the dict is a dict; all five keys present; `domain`/`score_type` are
  non-empty strings; `scores` is a dict of numeric values; `frame` is a dict
  or `None`; `diagnostics` is a list of well-formed `{"code", "message"}`
  dicts) and returns the envelope unchanged on success.
* **`null_frame(reason, *, code="frame_unavailable")`** — the canonical
  null-frame dict builder described above.
* **`EnvelopeError`** — the dedicated exception every rejection raises,
  carrying a machine-readable `.code` (one of the `CODE_*` constants in
  `coherence/schema.py`, e.g. `CODE_MISSING_KEY`, `CODE_INVALID_SCORES`,
  `CODE_INVALID_FRAME`) alongside a human-readable message, so callers can
  branch on the failure kind instead of parsing strings.

## The two-speed adoption rule

Envelope adoption across coherence-cli is **two-speed**, and that split is
deliberate rather than an oversight:

* **New nouns — quality, signal, investiture, and the `assess` report — emit
  the full shared envelope (`domain`, `score_type`, `scores`, `frame`,
  `diagnostics`) from day one.** They have no prior JSON contract to protect,
  so there is no reason for them to ship anything less than the complete
  shape.
* **Existing `meaning` verbs (`score`/`compare`/`trend`) keep their pinned
  v0.5.0 JSON shape** — `meaning_score`, `subdimensions`, `diagnostics` at the
  top level — **and gain only additive top-level keys**: `domain`,
  `score_type`, and `frame`. Nesting `meaning_score`/`subdimensions` under a
  `scores` map (i.e. fully converting `meaning` onto this envelope) is
  **deferred to an explicitly versioned future migration** — it is a breaking
  shape change for existing consumers and is not done implicitly as a side
  effect of this restructure.

In short: growing the `meaning` JSON is fine (backward compatible); reshaping
it is not — not yet, and not without its own version bump and migration note
when it happens.
