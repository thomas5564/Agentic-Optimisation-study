# Testbed v2: a baseline with many independent optimization opportunities

## Why
On the original baseline (`research/baseline/`), almost all of the available gain came from one or
two changes. In the recorded 30-iteration memory run, 29 of 30 plans fell in a single approach
category, and repeated failures were 1–2 iterations apart. With so few distinct ideas to remember,
a small cache holds nearly everything that matters, so a bounded (LRU) memory and full memory can't
be told apart. v2 spreads the cost across several independent hot spots so that useful history
covers more ideas and reaches further back.

## What changed
Only `app/db.py` differs from the original baseline. Routes, models, seed data, the UI, the API
contract, the official tests, the workload and the oracle are byte-identical, so v2 passes the same
suite and exact validation responses.

- `build.py` renders any combination of the fixes below, each with exactly one naive form and one
  optimized form. It holds the solutions and is researcher-only; agent workspaces are built only
  from run snapshots.
- `source/` is the rendered baseline plus `requirements.lock`. It was frozen with the existing
  `benchmarks.snapshot.freeze_baseline` into `research/baseline-v2/` (source hash `86606814…`).

| Fix | Approach | Naive baseline behaviour |
|---|---|---|
| `connection` | cache | New connection + schema DDL + commit on every call |
| `get_lookup` | query | Get-by-id scans and validates every note |
| `list_sql` | query | List/search loads all notes, then filters, counts and paginates in Python |
| `tag_index` | index | Tag filters scan a JSON column; no tag table or index (builds on `list_sql`) |
| `write_create`, `write_update`, `write_delete` | query | Create/update/delete each rescan all notes around the write (split per operation for the strict rule) |

There is no shared "load every note" helper: each slow function has its own inline scan. An earlier
draft shared one `_all_notes()` helper, and in both live smoke runs every plan replaced that helper
with SQL in one change, touching every operation at once (see **Scope rule** below).
| `no_vacuum` | other | `VACUUM` after every delete |
| `construct` | serialization | Every stored row is re-validated through Pydantic on read |

## Calibration (`calibration.json`; `calibrate.py`, no model calls)
- **Setup:** the frozen-final workload (2,000 notes, 100 cycles, 5 repetitions), epsilon 0.08, run
  through the unmodified `Evaluator` locally.
- **Correctness:** the official suite passed on the baseline, the full reference and every single fix.
- **Baseline:** 4.88 ms. Relative range 2.1%, well below epsilon. Cost is spread across operations:
  add 4.4, delete 5.0, get 4.4, list/search 4.5, update 9.0 ms.
- **Reference (all fixes):** 0.64 ms, so about **7.7× headroom**. The original baseline had
  3.9 → 1.0 ms.

**Each fix applied alone to the baseline** (4 of 7 clear epsilon on their own):

| Fix | Improvement |
|---|---|
| tag_index (with list_sql) | 35.5% |
| list_sql | 33.9% |
| write_lookups | 25.0% |
| get_lookup | 18.5% |
| no_vacuum | 0.9% |
| connection | 0.6% |
| construct | −2.8% |

**Greedy acceptance path** (best remaining fix each step; accepted only if the gain exceeds 8% over
its parent): 6 steps are accepted.

| Step | Fix | Gain over parent |
|---|---|---|
| 1 | list_sql | 33.9% |
| 2 | write_lookups | 40.0% |
| 3 | get_lookup | 52.6% |
| 4 | connection | 9.1% |
| 5 | tag_index | 10.5% |
| 6 | no_vacuum | 15.3% |
| 7 | construct | −0.6% (not accepted) |

There are six distinct acceptable steps across four approach categories. `connection` and
`no_vacuum` only clear epsilon once the scans are gone, so the order matters, and an optimizer that
remembers what was tried and what is left has something to gain.

## LRU capacity on v2
- The fixed Planner prompt is about 10,000 tokens: v2 `db.py` is about the same size as the original (4,164 vs 4,176 bytes).
- With the recorded largest memory entry (about 1,650 tokens) and the 12,000-token output reserve,
  a 32k deployment gives (32,768 − 10,000 − 12,000) / 1,650 ≈ 6.5, so **K = 6**. That evicts 24 of
  30 entries, starting at iteration 8.

## Protocol note
v2 is a new baseline. Results on it are **not comparable** to the recorded runs on the original
baseline, so all three arms (stateless, memory, memory_lru) must be run on v2. Configs:
`configs/lru-v2-smoke.yaml` (small benchmark) and `configs/lru-v2-study.yaml` (full workload).
Calibration was done on the host, not in the container, so absolute times differ from in-container
measurements; the per-run relative comparisons are what matter.

**Scope rule.** In the first v2 smoke run, all 6 plans bundled several fixes and all 6 failed the
same case-sensitive search test. v2 study runs therefore use `lru_memory.batch --single-change`,
applied identically to all three arms (see `lru_memory/README.md`).

**Case-sensitive `LIKE`.** The baseline connection sets `PRAGMA case_sensitive_like = ON`. In the
next smoke run, all 6 attempts wrote search as SQL `LIKE`, which ignores ASCII case by default, and
all failed the contract's case-sensitive search test. Memory entries record only
"correctness_failed", not which test failed, so no arm could learn from it. The pragma removes that
one trap equally for every arm. Known gap: `%` and `_` in a search act as wildcards under `LIKE`,
and the official tests don't catch this.

**Strict scope (`calibration-strict.json`).** In the overnight run without the rule, iteration 1
took 83–98% of each arm's total gain, so the arms could not differ. Under `--strict-scope` (one
public operation per patch), the greedy path restricted to compliant fixes is:

| Step | Fix | Before → after | Gain |
|---|---|---|---|
| 1 | list_sql | 4.93 → 3.15 ms | 36.1% |
| 2 | get_lookup | 3.15 → 2.22 ms | 29.4% |
| 3 | write_update | 2.22 → 1.56 ms | 29.7% |
| 4 | write_delete | 1.56 → 1.23 ms | 21.1% |
| 5 | write_create | 1.23 → 0.93 ms | 24.9% |
| 6 | connection | 0.93 → 0.84 ms | 9.2% |
| – | no_vacuum, construct | | 1.7%, 0.6% (not accepted) |

`tag_index` needs three operations, so under the rule it is only reachable with SQL triggers, and it
was left out of this path. In the strict live smoke run, every arm's first accepted step was 20–23%,
from changing `get_note` only.
