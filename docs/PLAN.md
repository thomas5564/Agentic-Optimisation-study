# Implementation Plan

## How to use this plan with Codex

Development instructions, specification, and this plan live in `docs/`. Start with the first incomplete milestone. Implement one requested milestone at a time; verify its acceptance checks, record evidence below, and stop before the next milestone unless the user authorizes multiple milestones.

Suggested first instruction:

```text
Read SPEC.md, PLAN.md, and AGENTS.md. Implement milestone 1 only.
Run its acceptance checks and fix failures. Update PLAN.md with the
commands run, results, and remaining issues. Do not begin milestone 2.
```

All commands below are target interfaces to implement, not claims that code already exists. Use `python -m ...` entry points and document environment setup in README.md. Milestones 1–2 are implemented and locally verified as of 2026-10-08. Milestones 3, 5, and 6 now have implemented and tested software. Milestone 4 has passed unpaid container integration; its explicitly requested live-model iteration is still open. Research execution remains open.

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

Evidence (2026-10-08 audit and repair):

- Original handoff reported 6 then 8 tests on another machine, but the contract,
  lock, bottleneck inventory, source snapshot, and several required tests were absent.
- `.venv/bin/python -m pytest tests/ -q`: **37 passed** in 3.52s,
  including real process restart persistence, exact case-sensitive tags, Unicode,
  parameterization, stale reads, and frozen validation responses.
- `.venv/bin/python -m benchmarks.snapshot --output research/baseline`: clean
  app/contract ZIP and SHA-256 manifest saved; source hash
  `4a97a1bbf4492970f2d33874ba2d2dccbc30f1a551a995490c45f46509a3636b`.
- Runtime/test dependencies are pinned in `requirements.lock`; public behavior is
  in `contracts/API.md` and representative exact errors in `contracts/validation-errors.json`.
- Research-only bottleneck inventory is in `research/BOTTLENECKS.md`.
- Baseline performance opportunities were preserved. The tag case correction is
  a functional alignment fix made before freezing, not an experimental optimization.

## Milestone 2 — Trustworthy benchmarking and profiling

- [x] Implement deterministic CRUD and list/search workload traces with explicit request dependencies and a reference response oracle.
- [x] Implement database reset, cache reset, warm-up, request timeout, repeated timing, and JSON output.
- [x] Support candidate schema initialization while preserving identical logical fixtures.
- [x] Record mean/p95 per operation, success/failure counts, raw samples, aggregate score, environment, and seeds.
- [x] Add profiling as a separate operation from latency measurement.
- [x] Measure unchanged-code noise and document how epsilon will be selected; no invented default final threshold.

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

Evidence (2026-10-08):

- `.venv/bin/python -m pytest tests/ -q`: **37 passed**. Includes real HTTP timeout,
  full-response and stale-cache rejection, candidate index preservation, state reset,
  benchmark lock, null invalid scores, correct median-of-means, and worker-thread profiling.
- `.venv/bin/python -m benchmarks.run --config configs/pilot.yaml --output research/evidence/baseline-2026-10-08`:
  five repetitions × 240 requests, **1,200 successful / 0 failed**, score **1.109207 ms**.
  Repetition means: **1.109207, 1.017898, 1.407070, 1.435663, 1.088293 ms**.
  Sample coefficient of variation **16.07%**; relative range **34.48%**.
  Raw requests, manifests, warm-ups, and operation summaries are archived in that directory.
- `.venv/bin/python -m benchmarks.profile --config configs/pilot.yaml --output research/evidence/profile-2026-10-08`:
  real endpoint profile captured separately; profile score is null.
- The first sandboxed server checks failed because localhost binding was forbidden;
  the same checks passed with local-server permission. No failures were hidden as scores.
- `.venv/bin/python -m pip check`: no broken requirements.
- Profiling captures endpoint work, not ASGI serialization/network overhead.
  The HTTPX timeout bounds transport inactivity; it is not a whole-request execution deadline.
- Local timing variance is too high for a small final epsilon. Keep epsilon unset;
  tune workload length/dataset and control machine conditions during a representative pilot.
  No final performance claim is made. Final configuration/acceptance validation belongs to later milestones.

## Milestone 3 — One iteration with mock agents

- [x] Define typed backend interfaces, role input/output JSON schemas, attempt records, and memory entries.
- [x] Implement prepare → profile → plan → develop → validate → benchmark → decide → audit → persist.
- [x] Enforce patch path allowlist and official harness immutability.
- [x] Implement deterministic acceptance, rollback, timeout handling, and atomic records.
- [x] Add mock cases for valid faster change, slower change, broken code, malformed output, no-op, and agent timeout.
- [x] Mock performance only in controller tests; label synthetic results explicitly and keep them out of real experiment folders.

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

Evidence (continuation, 2026-10-08):

- `controller.run` now performs prepare/profile/plan/develop/validate/measure/decide/audit/persist.
  Strict role schemas and runner-owned attempt/memory models are exported in `agents/schemas/`.
- Controlled mock cases cover improvement, regression, broken syntax, malformed output,
  no-op, role timeout, forbidden patch, and terminal audit failure. Synthetic timings
  occur only in unit tests; CLI mock runs use actual HTTP measurements.
- Focused tests verify deterministic epsilon decisions, exact hash rollback, factual
  memory, Auditor non-authority, and infrastructure-vs-candidate failures.
- Official tests execute in the trusted runner against separate candidate HTTP
  processes. Candidate code is not imported into the pytest process.
- Final smoke evidence: `/tmp/notes-mock-verified-2026-10-08` (three iterations per
  condition), with all raw role and measurement artifacts retained outside the repo.
- Full-suite and reproducibility verification details are recorded in
  `research/evidence/controller-2026-10-08/verification.json`.

## Milestone 4 — Codex backend and one live iteration

- [x] Inspect installed Codex CLI capabilities and document required setup; keep model explicit in config.
- [x] Implement fresh role invocation, structured outputs, process timeout, exit-code handling, and raw transcript capture.
- [x] Implement bounded role-specific permissions and a real isolated workspace with only explicit mounts.
- [x] Expose the agent-visible contract; exclude researcher files, source history, and other sessions.
- [x] Record CLI version, model, reasoning settings, prompt hashes, tool budget, elapsed time, and available usage.
- [x] Add mocked subprocess tests for errors and malformed outputs without paid calls.
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

Evidence (continuation, 2026-10-08):

- Host and container CLI inspected: `codex-cli 0.162.0-alpha.2`. Required flags are
  checked from actual `--help`; no resumed experimental sessions are used.
- Docker 29.6.1 started and a minimal runtime image built with pinned Python
  dependencies and Codex CLI. Immutable image:
  `sha256:385b5ef7719da065679daedf775a6a35567c9be0ddffa3143e659f21ab744238`.
- `.venv/bin/python -m agents.preflight --config configs/isolation-check.yaml`:
  passed actual read-only mount, fresh-history, and host/sibling sentinel checks.
- `.venv/bin/python -m controller.check_environment --config configs/isolation-check.yaml --output /tmp/notes-container-integration-01`:
  passed official baseline tests, 48/48 valid measured requests, and endpoint
  profiling in Linux containers. No inference calls or authentication needed.
- Subprocess unit tests cover malformed output, nonzero exits, timeout, tool/output
  budgets, redaction, context-compaction signals, and identical fresh-session flags.
- **Open check:** one explicitly requested live iteration with a chosen model and
  external CODEX_API_KEY. Live authentication, model availability, role behavior,
  exact token reporting, and live compaction handling are not certified yet.
- Agent CLI requires outbound inference connectivity. Default bridge networking
  is not an API-only egress allowlist; evaluator containers have no network.
  Filesystem/process boundaries are verified; use controlled egress for deployments
  exposing private services.

## Milestone 5 — Memory treatment and long-horizon runner

- [x] Implement identical condition pipelines with explicit memory injection only into the memory Planner.
- [x] Archive all attempts for researchers while exposing no historical artifacts to stateless agents.
- [x] Append complete ordered memory entries for accepted/rejected/failed attempts.
- [x] Add payload entry-count/hash checks, context-overflow detection, fixed horizon, and checkpoints.
- [x] Enforce identical role/output/repair budgets and report differential input usage.
- [x] Run three iterations per condition using mocks; perform live smoke runs only when requested.

Acceptance:

- Planner at iteration k receives exactly k−1 prior entries in the memory condition and zero in stateless.
- Developer and Auditor never directly receive the memory log.
- Known sentinel content in researcher logs and previous sessions cannot be accessed from agent workspaces.
- Accepted code persists in both conditions; rejected code never becomes the next parent.
- Full memory is either delivered or an explicit context-limit status ends the run; no silent truncation.

Evidence (continuation, 2026-10-08):

- Three-iteration runs for both conditions complete with mock roles and real
  measurements. Memory Planner input counts are exactly 0, 1, 2; stateless counts
  are 0, 0, 0. Developer/Auditor inputs contain no prior-attempt log.
- Tests check accepted-code retention, rejected and failed entries, full ordered
  history hashes, conservative input admission limits, and persistent context-limit
  termination. Nothing truncates or summarizes stored memory.
- The real container sentinel probe confirms host/sibling history is inaccessible
  and app/contract/schema mounts are read-only. Local mocks test input routing;
  they are not claimed to be an OS security sandbox.
- Live-model context delivery and compaction events remain part of milestone 4's
  unchecked live smoke, not something proven by a mock transcript.

## Milestone 6 — Resume, replication, and analysis

- [x] Implement state journal, stable attempt IDs, atomic step completion, recovery, and deduplicated memory append.
- [x] Add paired run configurations, randomized/alternating condition order, and a benchmark execution lock.
- [x] Export tidy attempt-level and request/repetition-level CSV tables.
- [x] Generate latency curves, correctness/request-success plots, checkpoint comparisons, and usage summaries.
- [x] Show raw run trajectories and uncertainty across independent runs.
- [x] Preserve incomplete/missing outcomes explicitly and separate mock, pilot, and final datasets.
- [x] Add final snapshot remeasurement and reproducibility manifests.

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

Evidence (continuation, 2026-10-08):

- Tests force interruption before/after decision, attempt commit, and memory
  materialization. Resume does not duplicate completed role calls or entries.
  Unresolved calls stop for explicit saved-result recovery or abandonment.
- Atomic journals include result hashes; manifests freeze config, source, runtime,
  prompts, budgets, baseline, and seeds. Full runner source is archived per run.
- Serial batch scheduling alternates condition order across pairs. Baseline/workload
  seeds are fixed and shared within/across pairs; model runs remain independent.
- Offline HTML/PNG and CSV reporting is implemented for attempts, requests,
  repetitions, operations, checkpoints, correctness, accepted changes, repeat
  classification, and available usage. Unknown usage/cost remains null.
- Tests verify identical/all-failed synthetic fixtures, incomplete pairs, duplicate
  run detection, cohort separation, and uncertainty computed across independent
  runs. Figures visibly label mock/synthetic data and carried measurements.
- Checkpoints and final snapshots are independently remeasured. Final protocol
  freezing requires completed real pilots of both conditions and epsilon above
  measured baseline noise; no final configuration has been fabricated.
- Completed-run resume and report generation were exercised on real mock smoke
  artifacts, without new agent calls.

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
| 2026-10-08 | 1–2 | Audited code/docs/proposal; repaired baseline artifacts and measurement scaffold | 37 tests; 1,200/1,200 requests; separate profile | Historical setup evidence |
| 2026-10-08 | 3–6 | Implemented controller, container backend, memory, resume, batches, analysis, protocol freeze | 92 tests; three mock iterations per condition; real container checks; offline plots | Milestone 4 live iteration and research execution remain open |

## Decisions and deviations

Record pilot decisions and protocol changes here, with reason and whether they affect comparison validity. Do not revise protocol silently based on which condition performs better.


### Recorded on 2026-10-08

- The supplied proposal was restored during the audit and read in full. Its core
  three-role, full-history Planner treatment and 10/15/20/25/30 checkpoints remain
  the target; none is claimed to exist yet.
- Report GET-by-ID independently from list/search. List/search is an explicit
  extension to the proposal's four CRUD operation metrics.
- Use successful/total as success rate; retain raw successful and failed counts.
  The proposal's successful/failed ratio is undefined at zero failures. The
  proposal's final runtime ratio repeats memory in both numerator/denominator;
  use stateless/memory speedup as already defined in SPEC.md. These are documented
  interpretation corrections, not observed findings.
- Implement exact case-sensitive tag matching and normalization before freezing
  the baseline; previous code silently folded case despite the specification.
- Retain inherited browser UI as an ancillary development convenience; do not
  expand it or include its requests in measurement.
- Use real loopback HTTP, fresh process/database per repetition, API-based seeding,
  and read-only warm-up. API seeding avoids imposing the baseline storage schema.
  Keep fixture/workload/oracle code under runner ownership, independent of app.seed.
- Existing tracked tmp/ and benchmark-output/ artifacts contain invalid search
  responses and must not be treated as valid performance evidence.
- Process separation in the benchmark is not security isolation. A live agent
  comparison remains blocked on milestone 4's real access controls, not on prompts.


### Continuation decisions (2026-10-08)

- User authorized implementation of all remaining milestones. Live/paid study
  execution remains separate from software implementation.
- Developer produces schema-validated complete-file edits; the runner applies
  them. All role app/contract mounts are read-only, a stricter boundary than
  letting Developer directly modify the workspace. Both conditions use this
  identical protocol. The official harness is never mounted for an agent.
- Evaluation runs candidate servers in separate processes and tests from the
  protected runner. Live candidate evaluation uses a network-disabled container.
- Parent/candidate *batches* alternate order by iteration; repetitions within a
  batch remain serial and deterministic. No synthetic performance enters CLI runs.
- Full runner source and role prompts are archived with each new run. Completed
  stages are reused; an unknown in-flight model call is never automatically retried.
- Final protocol is deliberately unfilled until real pilot evidence exists. Default
  smoke epsilon is only for exercising acceptance control flow. Current mock
  condition differences are timing noise, not evidence about memory effects.
