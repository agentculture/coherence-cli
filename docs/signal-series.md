# The signal series schema

`coherence.signal.schema` (`coherence/signal/schema.py`) defines the one input
shape every `coherence signal` engine consumes — trend, pattern, resonance,
forecast, and the `collect` glue that builds series files. It is the contract
for the whole signal layer, so it is documented here in full; the module
docstring points back to this file.

The signal layer is deliberately **source-agnostic**. It never asks *what*
produced a series or *what the numbers mean* — it consumes an ordered list of
points, each carrying a bag of arbitrarily named numeric values, and runs the
same trajectory math over any of them. A series hand-authored for warehouse
throughput and a series converted from `coherence meaning trend` output flow
through the identical loader and the identical engines.

## The series shape

A series is a JSON object with two top-level keys:

```json
{
  "domain": "meaning",
  "points": [
    {
      "id": "v1.md",
      "index": 0,
      "timestamp": null,
      "values": {"meaning_score": 0.41, "agency": 0.33},
      "frame": null
    }
  ]
}
```

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `domain` | `str` or absent | optional | A human-readable label naming the dimension that produced the series (`"meaning"`, `"quality"`, `"investiture"`, …). The signal layer **never branches on it** — it is documentation, not control flow. Absent or non-string normalizes to `None`. |
| `points` | `list` | yes | The ordered list of measurement points. Order is the source of truth for series position. |

### Per-point fields

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | `str` | expected | A human-readable label for the point — a filename, a version tag, a run id. Missing or non-string is synthesized as `"point-<pos>"` with a diagnostic. |
| `index` | `int` | optional | The point's position in the series. **Canonicalized to the list position** on load; a provided value that disagrees earns an `index_mismatch` diagnostic (the list order always wins). |
| `timestamp` | `str`/`number`/`null` | nullable | An optional wall-clock label (an ISO-8601 string or an epoch number) or `null`. The signal layer is **unitless and per-step** — it does no time-axis math — so the timestamp is carried through untouched for display and provenance only. Absent normalizes to `null`. |
| `values` | `object` | yes | An open map of **arbitrarily named numeric values**. See below. |
| `frame` | `object` or `null` | optional | The per-point measurement-provenance block. See below. |

## `values` — arbitrary named numeric fields

`values` is the payload the signal engines actually analyze. Its keys are
**caller-defined and never enumerated by the signal layer** — `meaning_score`,
`throughput`, `widget_gain`, whatever the producer named them. Its values must
be real numbers.

The loader is **robust by contract**: a malformed entry is *skipped with a
diagnostic*, never a crash. Specifically, within one point's `values`:

- A **non-string key** is skipped (`series_invalid_value_name`).
- A **null**, **string**, or otherwise **non-numeric** value is skipped
  (`series_non_numeric_value`).
- A **boolean** value is skipped — `bool` is an `int` subclass in Python, but a
  flag is not a measurement, so `true`/`false` are **not** treated as `1.0`/`0.0`
  (`series_non_numeric_value`, matching the shared envelope's rule).
- A surviving numeric value is normalized to a `float`.
- A missing or non-object `values` yields an empty `values` map plus a
  diagnostic (`series_invalid_values`); the point still survives.

So a point can legitimately end up with `values == {}` (everything was
skipped) — the point is kept, and downstream engines simply find no field to
analyze there. Nothing is silently dropped: every skip leaves a diagnostic
naming the point and the offending field.

## `frame` — optional per-point provenance

`frame` is the optional per-point provenance block: the measurement frame
(embedding model, endpoint, anchor set, projection method, …) that produced
*this* point's values. It mirrors the `frame` key of the shared measurement
envelope in [`docs/envelope.md`](envelope.md) — the same provenance block, now
attached per point instead of per measurement.

- `frame` may be a **dict**, an explicit **`null`**, or **absent**.
- Absent or `null` normalizes to an explicit `None` — never a missing key, so a
  downstream reader can always ask "does this point declare a frame?" without a
  `KeyError`.
- A `frame` that is present but neither an object nor `null` is dropped to
  `None` with a `series_invalid_frame` diagnostic (mirroring the envelope's
  "`frame` is a dict or `None`" rule).

Why per-point rather than per-series: a series can be **collected across
different measurement frames** — e.g. two artifacts scored under different
embedding models. Keeping the frame on each point lets a later **mixed-frame
guard** (the frames task) walk the points, notice that they were measured under
different gauges, and warn — turning a silent cross-gauge comparison error into
a visible diagnostic. Points from a single trend run share one frame; points
from a hand-collected series may not.

## The loader contract

`load_series(data)` returns a normalized, typed `Series`:

```python
from coherence.signal.schema import load_series

series = load_series(raw)          # raw: a dict, or a JSON str/bytes
series.domain                      # str | None
series.points                      # list[SeriesPoint], in series order
series.diagnostics                 # list[{"code", "message"}], mutable
series.field_names()               # set of every numeric value name present
series.to_dict()                   # the input-schema dict (round-trips)
```

Each `SeriesPoint` carries `id`, `index`, `timestamp`, `values`
(`dict[str, float]`), and `frame` (`dict | None`).

Two rules govern how failure is reported, and the split is deliberate:

1. **Malformed *values* never raise.** Everything skipped or repaired inside a
   point is recorded in `series.diagnostics`, the same
   `{"code": str, "message": str}` shape used by `coherence.meaning.diagnostics`
   and the shared envelope. The list is **mutable and appendable on purpose**,
   so a later task (the mixed-frame guard) can plug in by walking
   `series.points` and appending its own diagnostics.
2. **Top-level structural failure raises `SeriesError`.** When the input is not
   a mapping, is an unparseable JSON string, lacks the `points` key, or `points`
   is not a list, there is nothing to normalize — so the loader raises
   `SeriesError` carrying a machine-readable `.code` (mirroring
   `coherence.schema.EnvelopeError`). This makes "this is not a series at all"
   fail loudly instead of silently returning an empty series, while
   data-quality issues stay inside `diagnostics`.

### Diagnostic and error codes

| Code | Kind | Meaning |
| --- | --- | --- |
| `series_not_a_mapping` | raised | Input is not an object (and not a JSON string encoding one). |
| `series_invalid_json` | raised | A `str`/`bytes` input was not valid JSON. |
| `series_missing_points` | raised | The `points` key is absent. |
| `series_points_not_a_list` | raised | `points` is present but not a list. |
| `series_invalid_domain` | diagnostic | `domain` was present but not a string; treated as absent. |
| `series_point_not_a_dict` | diagnostic | A `points` entry was not an object; skipped. |
| `series_missing_id` | diagnostic | A point's `id` was missing/invalid; synthesized `point-<pos>`. |
| `series_invalid_index` | diagnostic | A point's `index` was not an int; list position used. |
| `series_index_mismatch` | diagnostic | A point's `index` disagreed with its list position; position used. |
| `series_invalid_values` | diagnostic | A point's `values` was missing or not an object; treated as empty. |
| `series_invalid_value_name` | diagnostic | A value name was not a string; that entry skipped. |
| `series_non_numeric_value` | diagnostic | A value was null/non-numeric/boolean; that entry skipped. |
| `series_invalid_timestamp` | diagnostic | A point's `timestamp` was not a string/number/null; set to null. |
| `series_invalid_frame` | diagnostic | A point's `frame` was neither an object nor null; set to null. |

## Building a series from `meaning trend` output

`series_from_meaning_trend(trend_json, *, domain="meaning")` is the
source-agnosticism bridge in code form. It flattens each `meaning trend` point's
`meaning_score` and every subdimension into a single `values` bag under their
own names, and returns the **input-schema dict** (not a `Series`) so it loads
through the exact same `load_series` as any hand-written series:

```python
from coherence.meaning.trend import trend
from coherence.signal.schema import load_series, series_from_meaning_trend

trend_json = trend(["v1.md", "v2.md", "v3.md"])
series = load_series(series_from_meaning_trend(trend_json))
series.field_names()
# {"meaning_score", "consequence", "agency", "causality", "affordance", "future_constraint"}
```

Each point's `id` comes from the trend result's `paths`. Any top-level `frame`
block on the trend result (added by a later frames task) is carried onto **every**
point, because a single trend run shares one embedding frame across its points;
when the trend result has no frame, each point's frame is `null`. This is the
proof of source-agnosticism the MVP requires: the same loader and the same
engines serve a converted `meaning trend` series and a hand-authored one with
invented value names, with no per-source code path.

## Planned, not yet built

The MVP ships trend, pattern, and resonance over this schema. Richer analyses —
harmonic, wave, decay, and standalone interference families — are documented as
planned and will be built only once real series data exists to validate them.
They will consume this same series schema unchanged; no field here is expected
to be removed or retyped to accommodate them.
