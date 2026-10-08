# Implementation Plan

## How to use this plan with Codex

Place SPEC.md, PLAN.md, and AGENTS.md at the development repository root. Start with milestone 1. Implement one requested milestone at a time; verify its acceptance checks, record evidence below, and stop before the next milestone unless the user authorizes multiple milestones.

Suggested first instruction:

```text
Read SPEC.md, PLAN.md, and AGENTS.md. Implement milestone 1 only.
Run its acceptance checks and fix failures. Update PLAN.md with the
commands run, results, and remaining issues. Do not begin milestone 2.
```

All commands below are target interfaces to implement, not claims that code already exists. Use `python -m ...` entry points and document environment setup in README.md. No milestones are implemented yet.

## Milestone 1 — Correct baseline notes application

- [x] Create Python project metadata, dependency lock, app package, and README setup instructions.
- [x] Implement SPEC.md endpoints, data model, SQLite persistence, deterministic seed generation, and agent-visible API contract.
- [x] Build a correct but reasonably inefficient baseline with several realistic optimization opportunities; keep inventory in research/ only.
- [x] Implement official tests for CRUD, filters, pagination, validation, missing IDs, Unicode, persistence, and cache-sensitive mutations.
- [x] Record the baseline source hash; preserve it as the starting snapshot.

Acceptance:

- `python -m pytest tests/ -q` passes.
- An application restart preserves completed mutations.
- Seeding twice with the same seed produces the same logical data.
- Search/filter semantics and error responses are documented and tested.
- No artificial sleeps, planted correctness bugs, or optimization-hint comments.

Evidence:

- Command run: `cd /Users/thomaschoo/Downloads/comp-690 && . .venv/bin/activate && python -m pytest tests/ -q`
- Result: 6 passed in 0.22s
- The baseline app, persistence model, and deterministic seed logic were created and verified.
- Remaining work: proceed to Milestone 2 only when explicitly requested.

## Milestone 2 — Trustworthy benchmarking and profiling

- [ ] Implement deterministic CRUD and list/search workload traces with explicit request dependencies and a reference response oracle.
- [ ] Implement database reset, cache reset, warm-up, request timeout, repeated timing, and JSON output.
- [ ] Support candidate schema initialization while preserving identical logical fixtures.
- [ ] Record mean/p95 per operation, success/failure counts, raw samples, aggregate score, environment, and seeds.
- [ ] Add profiling as a separate operation from latency measurement.
- [ ] Measure unchanged-code noise and document how epsilon will be selected; no invented default final threshold.

Target interfaces:

```bash
python -m benchmarks.run --config configs/pilot.yaml --output /tmp/notes-benchmark
python -m benchmarks.profile --config configs/pilot.yaml --output /tmp/notes-profile
```

Acceptance:

- Repeated resets produce the same initial logical state and trace.
- A deliberately wrong response and a stale cache fail the oracle.
- Timeouts are counted as failures; failed responses cannot improve the acceptance score.
- Profiling overhead is excluded from timed results.
- Baseline variability is reported numerically with raw measurements.

Evidence: not started.

## Milestone 3 — One iteration with mock agents

- [ ] Define typed backend interfaces, role input/output JSON schemas, attempt records, and memory entries.
- [ ] Implement prepare → profile → plan → develop → validate → benchmark → decide → audit → persist.
- [ ] Enforce patch path allowlist and official harness immutability.
- [ ] Implement deterministic acceptance, rollback, timeout handling, and atomic records.
- [ ] Add mock cases for valid faster change, slower change, broken code, malformed output, no-op, and agent timeout.
- [ ] Mock performance only in controller tests; label synthetic results explicitly and keep them out of real experiment folders.

Target interface:

```bash
python -m controller.run --backend mock --condition stateless --iterations 1 --config configs/smoke.yaml --output /tmp/notes-mock
```

Acceptance:

- Only a correct improvement beyond configured epsilon is accepted.
- Every rejection preserves the exact parent source hash.
- Every attempt creates a factual record; unavailable metrics are null.
- Auditor output cannot override measured data or the controller's decision.
- Syntax, startup, correctness, and infrastructure failures remain distinguishable.

Evidence: not started.

## Milestone 4 — Codex backend and one live iteration

- [ ] Inspect installed Codex CLI capabilities and document required setup; keep model explicit in config.
- [ ] Implement fresh role invocation, structured outputs, process timeout, exit-code handling, and raw transcript capture.
- [ ] Implement bounded role-specific permissions and a real isolated workspace with only explicit mounts.
- [ ] Expose the agent-visible contract; exclude researcher files, source history, and other sessions.
- [ ] Record CLI version, model, reasoning settings, prompt hashes, tool budget, elapsed time, and available usage.
- [ ] Add mocked subprocess tests for errors and malformed outputs without paid calls.
- [ ] When live execution is requested, run one complete iteration and inspect its artifacts.

Target interface:

```bash
python -m controller.run --backend codex --condition stateless --iterations 1 --config configs/smoke.yaml --output /tmp/notes-live-smoke
```

Acceptance:

- Missing credentials, model, or isolation prerequisites produce actionable errors without exposing secrets.
- Planner/Auditor cannot edit the app; Developer cannot modify the official harness.
- Agents cannot read sibling workspaces, developer project documents, history, or prior session state.
- One requested live iteration produces real plan, patch, measured validation, and audit evidence.
- If live execution is unavailable, report the specific incomplete check; do not mark the milestone fully passed.

Evidence: not started.

## Milestone 5 — Memory treatment and long-horizon runner

- [ ] Implement identical condition pipelines with explicit memory injection only into the memory Planner.
- [ ] Archive all attempts for researchers while exposing no historical artifacts to stateless agents.
- [ ] Append complete ordered memory entries for accepted/rejected/failed attempts.
- [ ] Add payload entry-count/hash checks, context-overflow detection, fixed horizon, and checkpoints.
- [ ] Enforce identical role/output/repair budgets and report differential input usage.
- [ ] Run three iterations per condition using mocks; perform live smoke runs only when requested.

Acceptance:

- Planner at iteration k receives exactly k−1 prior entries in the memory condition and zero in stateless.
- Developer and Auditor never directly receive the memory log.
- Known sentinel content in researcher logs and previous sessions cannot be accessed from agent workspaces.
- Accepted code persists in both conditions; rejected code never becomes the next parent.
- Full memory is either delivered or an explicit context-limit status ends the run; no silent truncation.

Evidence: not started.

## Milestone 6 — Resume, replication, and analysis

- [ ] Implement state journal, stable attempt IDs, atomic step completion, recovery, and deduplicated memory append.
- [ ] Add paired run configurations, randomized/alternating condition order, and a benchmark execution lock.
- [ ] Export tidy attempt-level and request/repetition-level CSV tables.
- [ ] Generate latency curves, correctness/request-success plots, checkpoint comparisons, and usage summaries.
- [ ] Show raw run trajectories and uncertainty across independent runs.
- [ ] Preserve incomplete/missing outcomes explicitly and separate mock, pilot, and final datasets.
- [ ] Add final snapshot remeasurement and reproducibility manifests.

Target interfaces:

```bash
python -m controller.resume --run-dir /path/to/existing-run
python -m analysis.report --runs-dir /path/to/final-runs --output /path/to/report
```

Acceptance:

- Forced interruption before/after acceptance and memory append resumes with no duplicate attempt, agent call for a completed step, or memory entry.
- Archived result fixtures regenerate figures without invoking agents.
- Identical or all-failed synthetic fixtures yield mathematically valid summaries with explicit missing metrics.
- No significance calculation treats iterations as independent runs.
- Manifest permits identification of exact code, config, workload, prompts, and versions used.

Evidence: not started.

## Experiment execution — after implementation

- [ ] Run a requested 10-iteration pilot and review noise, runtime, token usage, and remaining optimization headroom.
- [ ] Freeze model, prompts, epsilon, workload, dataset, replication count, timeouts, and repair budget in configs/final.yaml.
- [ ] Record the final protocol hash before observing final outcomes.
- [ ] Start all final runs from the untouched baseline; target 5 replicate pairs, or document a smaller budget-driven count.
- [ ] Execute 30 iterations with checkpoints at 10/15/20/25/30, serial benchmarks, and recorded condition order.
- [ ] Remeasure final snapshots, generate analysis, and document limitations and deviations.

Do not launch the full experiment as a side effect of building the software. Once the user requests a specific live batch, run that batch without repeatedly asking permission for its normal steps.

## Progress log

| Date | Milestone | Changes | Verification | Remaining issues |
| --- | --- | --- | --- | --- |
| — | — | Planning documents created; implementation not started | — | All milestones pending |

## Decisions and deviations

Record pilot decisions and protocol changes here, with reason and whether they affect comparison validity. Do not revise protocol silently based on which condition performs better.
