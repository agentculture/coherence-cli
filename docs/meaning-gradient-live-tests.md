# Meaning Gradient — live test report

Manual, end-to-end verification of the `coherence meaning` noun against a **live
embedding gear**, run on 2026-07-04 during the Meaning Gradient MVP build
(branch `feat/meaning-gradient`, v0.5.0). These exploratory checks complement —
they do not replace — the automated offline suite (133 tests, run in CI with
zero network).

## What, why, how, and what it means

- **What was live-tested.** The three CLI verbs end-to-end (`coherence meaning
  score` / `compare` / `trend`), the CLI introspection surface (bare noun,
  `explain`, `learn`), and the error contract (exit codes 0/1/2) — driven through
  the real `coherence` command against a **live** embedding endpoint, plus the
  falsifiability ordering test run on **real** embeddings.
- **Why live-test at all.** The automated suite is deliberately offline: it injects
  synthetic or recorded vectors so CI needs no network. That proves the *machinery*
  but leaves three things a unit test cannot: (1) that the real HTTP embedding
  integration actually works against a served model; (2) that the anchor-axis method
  produces **correct orderings on real embeddings** — the central falsifiable claim,
  which synthetic vectors can only rehearse; and (3) that the error/exit-code
  contract behaves in the real environment (e.g. a genuinely unreachable gear).
- **How.** Point the client at the live gear
  (`COHERENCE_EMBED_URL=http://localhost:8001/v1`,
  `COHERENCE_EMBED_MODEL=Qwen/Qwen3-Embedding-0.6B`,
  `COHERENCE_EMBED_TIMEOUT=120`), record real vectors for the committed fixtures
  with `scripts/refresh_meaning_vectors.py`, then run the CLI verbs and the ordering
  test and read the JSON output.
- **What it means.** The instrumentation is empirically sound: real embeddings order
  high-meaning artifacts above low-meaning ones *without anchor tuning*, rewrites
  register as measurable gains, and the offline diagnostics agree with the embedding
  signal. This validates that the signal is **measurable and directionally correct**
  — it does **not** yet claim predictive validity (that is the deferred phase-3
  experiment, issue #6). Instrumentation first, so the thesis stays falsifiable.

## Environment

| Setting | Value |
| --- | --- |
| Embedding endpoint | `http://localhost:8001/v1` (multi-lobe router) |
| Embedding model | `Qwen/Qwen3-Embedding-0.6B` (1024-dim) |
| Timeout | `COHERENCE_EMBED_TIMEOUT=120` (lobes lazy-load on first request) |
| Fixtures | `tests/fixtures/meaning/` (4 high/low pairs + a 3-point rewrite series) |

The lobe cold-starts on the first request (a fresh call can exceed the default
30s timeout — the reason `COHERENCE_EMBED_TIMEOUT` was added), then serves warm.

## 1. CLI surface and error contract (offline)

These need no embeddings and were exercised with the gear both up and down.

| Invocation | Expected | Result |
| --- | --- | --- |
| `coherence meaning` (bare) | noun overview, exit 0 | overview listing `score`/`compare`/`trend`, exit 0 |
| `coherence explain meaning` | markdown docs, exit 0 | full catalog entry rendered |
| `coherence learn --json` | lists meaning verbs | `["meaning","score"]`, `["meaning","compare"]`, `["meaning","trend"]` present |
| `coherence meaning trend f1` (one file) | user error, exit 1 | `error: meaning trend needs at least 2 files` + hint, exit 1 |
| `coherence meaning score f` (gear down) | env error, exit 2 | `error: Embedding endpoint unreachable ...` naming `COHERENCE_EMBED_URL`, exit 2 |

The gear-down case was also checked with `--json`: it emits
`{"code": 2, "message": ..., "remediation": ...}` to stdout, exit 2 — the
structured error contract holds in both text and JSON modes.

## 2. Recording real vectors

```console
$ COHERENCE_EMBED_URL=http://localhost:8001/v1 \
  COHERENCE_EMBED_MODEL=Qwen/Qwen3-Embedding-0.6B \
  python scripts/refresh_meaning_vectors.py
recorded 72 vectors -> tests/fixtures/meaning/recorded_vectors.json
```

72 = every fixture artifact text plus every anchor line across all six axes.
These vectors are committed so the ordering test runs offline in CI.

## 3. Falsifiability: the ordering test (real vectors)

With the recorded vectors present, the previously-skipped ordering test runs for
real and passes — no anchor tuning was required:

```console
$ pytest tests/test_meaning_ordering.py -v
test_fixture_inventory_is_sane                     PASSED
test_high_outranks_low[auth_middleware]            PASSED
test_high_outranks_low[cache_stampede]             PASSED
test_high_outranks_low[db_migration]               PASSED
test_high_outranks_low[payment_webhook]            PASSED
test_rewrite_series_is_non_decreasing              PASSED
6 passed
```

Every high-meaning fixture scores strictly above its paired low-meaning one, and
the rewrite series is monotonic non-decreasing in `meaning_score`.

## 4. Live scoring — `auth_middleware` pair

`coherence meaning score <fixture> --json`, gear live:

| Field | high | low |
| --- | --- | --- |
| `meaning_score` | **0.558** | **0.459** |
| `consequence` | 0.564 | 0.446 |
| `agency` | 0.567 | 0.506 |
| `causality` | 0.499 | 0.444 |
| `affordance` | 0.498 | 0.423 |
| `future_constraint` | 0.566 | 0.511 |
| `diagnostics` | `[]` | `missing_consequence`, `missing_owner`, `missing_next_action` |

The high artifact outranks the low one on the scalar **and** on every
subdimension, while the offline rule engine independently flags the vague
artifact for the three missing properties. Exit code 0.

## 5. Live compare — `low` → `high`

`coherence meaning compare auth_middleware.low.txt auth_middleware.high.txt --json`:

| Signal | delta (after − before) |
| --- | --- |
| `meaning_score` | +0.099 |
| `consequence` | +0.118 |
| `agency` | +0.062 |
| `causality` | +0.055 |
| `affordance` | +0.074 |
| `future_constraint` | +0.056 |

Every delta is positive — rewriting the vague artifact into the rich one is
measured as a meaning gain across all dimensions.

## 6. Live trend — rewrite series `v1` → `v2` → `v3`

`coherence meaning trend series/v1.txt series/v2.txt series/v3.txt --json`:

| Point | `meaning_score` |
| --- | --- |
| v1 | 0.454 |
| v2 | 0.528 |
| v3 | 0.543 |

`n = 3`, so second differences (`f''`, acceleration) are available alongside
first differences (`f'`, velocity). The score climbs monotonically as the
artifact is rewritten, and the first-difference series is positive and
decelerating (a large v1→v2 gain, a smaller v2→v3 gain).

## Conclusion

The full pipeline works end-to-end against the real embedding gear: scoring,
compare deltas, and trend derivatives all behave as specified, the error
contract maps cleanly to exit codes 0/1/2, and — most importantly — the
anchor-axis method orders meaning correctly on real embeddings without tuning.
This is the empirical evidence the MVP was built to produce; the phase-3
experiment (deferred, see issue #6) is what tests predictive validity.

---

*Generated by Claude Code during the Meaning Gradient MVP build (issue #6, PR #7).*
