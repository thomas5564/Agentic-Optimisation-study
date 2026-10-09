# Memory-Guided Long-Horizon Code Optimization

## Purpose

COMP 690-158 research implementation for Thomas Choo and Jaymeson Koh.
Investigate whether an explicit, continuously accumulating history of optimization attempts helps an LLM optimize the same evolving application over 30 iterations, and whether its benefit grows, plateaus, or diminishes.

This specification operationalizes the project proposal. Engineering choices below are proposed defaults, not claims from the proposal. Freeze pilot-dependent settings before final experiments and record any deviations.

## Scope and stack

- Python, FastAPI, SQLite, pytest, a Python HTTP workload driver, and Python profiling.
- A Python controller invokes Planner, Developer, and Auditor through a replaceable agent backend; implement a mock backend before a Codex CLI backend.
- No frontend, distributed agent framework, vector database, memory retrieval, or memory summarization.
- Keep dependencies small and lock their versions. Support development on macOS or Linux; use one fixed environment for final measurements.
- Do not implement or run a paid experiment merely because this specification describes it.

## Application contract

Notes have integer `id`, string `title`, string `body`, and a list of unique string `tags`. IDs are server-generated; all mutations persist across application restarts. Specify validation limits and exact error bodies in an agent-visible API contract during milestone 1 and freeze them before agent experiments.

| Operation | Endpoint | Contract |
| --- | --- | --- |
| Add | POST /notes | Return 201 and the persisted note |
| Get | GET /notes/{id} | Return 200 with note; unknown ID returns 404 |
| List/search | GET /notes | Return notes with total count, offset, and limit |
| Update | PUT /notes/{id} | Replace title, body, and tags; return updated note; unknown ID returns 404 |
| Delete | DELETE /notes/{id} | Return 204; subsequent retrieval returns 404 |

List/search supports case-sensitive substring matching over title or body, exact tag filtering, and ascending ID order before pagination. Combined filters use AND. Default offset is 0 and limit is 20; limit must be 1–100 and offset nonnegative. Invalid input returns 422. Empty search matches all notes. Preserve these semantics across optimizations.

Add list/search as a separately reported operation alongside the proposal's four CRUD operations. It provides realistic query and serialization work; disclose this extension in the report.

Baseline code must be correct but contain plausible performance opportunities, such as unnecessary row materialization, repeated tag queries, repeated transformations, and missing useful indexes. Never add artificial sleeps, deliberate errors, or comments revealing the intended optimization. Store the intended bottleneck inventory only in researcher materials. Do not optimize the baseline while building it.

Correctness coverage must include normal CRUD, validation, missing IDs, filter combinations, deterministic pagination, Unicode, persistence after restart, and read-after-update/delete. Test cache invalidation and SQL parameterization. Official correctness evaluation is controlled by the runner, not the agents.

## Repository and isolation boundaries

Suggested development layout:

```text
app/                  # Agent-editable application and schema initialization
contracts/            # Sanitized API contract visible to agents
tests/                # Official correctness tests; researcher-controlled
benchmarks/           # Dataset, workloads, oracle, measurements, profiling
controller/           # State machine, validation, snapshots, acceptance
agents/               # Backend interface, Codex adapter, prompts, schemas
analysis/             # CSV exports and figures
configs/              # Pilot and final experiment settings
research/             # Bottleneck inventory and researcher-only notes
SPEC.md
PLAN.md
AGENTS.md
```

Run artifacts and experimental workspaces live outside agent-accessible development roots. An experimental agent receives only the current app snapshot, sanitized contract, permitted current evidence, and its explicit role inputs. Do not copy these three development documents into experimental workspaces.

Use actual filesystem/process isolation, preferably containers with explicit mounts, rather than instructions alone. Agents cannot read archived runs, prior sessions, host project files, Git history, sibling workspaces, or other runs. Separate their session state. Supply authentication by the supported mechanism without exposing researcher home directories. Restrict writable paths to the candidate app and ephemeral tooling state. Forbid benchmark/test/controller modifications, symlink escapes, and files outside the allowlist. Validate changed paths before execution. If the selected backend cannot enforce these boundaries, label the run unsuitable for final comparison until fixed.

## Experimental conditions

| Input | Stateless | Memory-guided |
| --- | --- | --- |
| Current accepted code and current profile | Yes | Yes |
| API contract, objective, tool and repair budgets | Same | Same |
| Previous conversation | No | No |
| Full history of prior attempts | No | Planner only |

Both conditions retain accepted code changes. Stateless means no explicit historical experience, not resetting the application every iteration. Fresh role invocations are required; never resume prior experimental conversations.

Only the Planner receives accumulated memory. The Developer sees the current plan and code; the Auditor sees only the current plan, patch, measured evidence, and acceptance decision. Any information the Planner incorporates into its current plan is an intended consequence of the treatment.

Use identical base prompts, model, reasoning configuration, permissions, timeout, and output/repair budgets. The sole intentional input difference is the Planner memory payload. Do not claim equal total input-token cost: memory increases it. Record settings and actual usage when available; unknown usage is null, not zero.

## Iteration protocol

1. Export the last accepted app snapshot into a fresh candidate workspace.
2. Profile the accepted code using the current fixed workload; separate profiling from timed measurement.
3. Invoke Planner with current code, contract, objective, profile, and condition-appropriate memory. Require one focused hypothesis, proposed change, and expected risks in schema-validated JSON.
4. Invoke Developer to implement that plan. Development checks are allowed within a fixed timeout, but official evaluation remains external. Default: one Developer invocation and no post-evaluation repair invocation per iteration.
5. Validate the patch allowlist, syntax/imports, startup, and official correctness suite.
6. If correct, measure parent and candidate on the fixed workload with identical reset/warm-up procedures. Otherwise skip performance acceptance and retain failure evidence.
7. Controller applies the deterministic acceptance rule. Accepted candidate becomes the next parent; otherwise preserve the previous parent exactly.
8. Invoke Auditor to interpret current evidence. Runner supplies factual metrics; Auditor cannot overwrite them or decide acceptance.
9. Persist the attempt atomically and append one memory entry. Archive entries for both conditions, but expose them only to the memory Planner on subsequent iterations.

Count incorrect, timed-out, no-op, and rejected optimization attempts toward the 30-iteration horizon. Classify infrastructure failures separately: pause or resume the same iteration, never convert missing evidence into a successful attempt. Keep role retries bounded and logged. A terminal Auditor failure produces a factual entry with `audit_status=failed` and no invented explanation.

## Measurements and acceptance

Generate deterministic notes, tags, and request traces from recorded seeds. Choose data volume, request mix, concurrency, warm-up count, and repetitions during the pilot and freeze them for final runs. Start with concurrency 1 and five measurement repetitions; increase only to resolve demonstrated measurement noise. Ensure the workload exercises all operations and is long enough for useful timing.

Restore the original logical database before each repetition and warm-up. Reset process caches and use the same warm-up trace. Seed via the candidate's schema initialization so valid index/schema optimizations are preserved. Verify logical fixture equivalence. Request IDs and dependencies must be deterministic; maintain a reference state oracle to validate responses, not only HTTP status codes. Expected 404/422 responses in negative correctness tests are not workload failures.

Collect mean and p95 latency per endpoint, completed/failed/timed-out requests, startup/import status, test outcomes, total workload elapsed time, and response semantic mismatches. Use a monotonic clock and fixed request timeout. Count timeouts as failures, not missing fast requests. Record raw repetitions. Run profiler measurements separately and record tool/version.

Primary score: median across repetitions of each repetition's mean request latency over the fixed, successful workload. Report per-operation means separately. Failed candidates cannot be accepted and have no valid speedup score.

Measure the unchanged baseline repeatedly in the pilot. Select a minimum relative improvement threshold `epsilon` larger than the observed noise and freeze it in the final configuration. Missing epsilon blocks final runs. Alternate parent/candidate measurement order. Accept only if all official checks pass, all timed-workload responses are valid, and `(parent_score - candidate_score) / parent_score > epsilon`. Archive the raw data and reason. This greedy rule deliberately rejects temporary regressions and inconclusive improvements.

No concurrent benchmark processes. Fix hardware/runtime, worker count, dependencies, workload, and power conditions as far as practical; record environmental changes. Do not allow agents to disable durability, change semantics, special-case benchmark inputs, or alter the harness.

## Memory and records

Each attempt record includes schema version, run/iteration/condition, parent/candidate hashes, configuration hash, plan, patch, status, raw metric references, factual acceptance decision/reason, audit, timings, and available token usage. Archive exact role inputs/outputs with secrets redacted.

Each memory entry includes iteration, parent/candidate hash, hypothesis, attempted change, correctness result, before/after score when measured, acceptance decision, observed evidence, interpretation, limitations, and audit status. Store factual observations separately from speculative interpretation. Include rejected and failed attempts.

Serialize the complete ordered memory deterministically. Keep entries concise at creation using the same audit schema in both conditions, but never delete, retrieve a subset, or retrospectively summarize prior entries. Track payload size and exact entry count. If context limits prevent full-history delivery, stop and report an explicit protocol limitation; do not silently truncate or compact memory.

## Pilot and final evaluation

- Smoke test: 3 iterations per condition using mock agents, then an explicitly requested live smoke run.
- Pilot: up to 10 iterations per condition to evaluate noise, runtime, cost, and optimization headroom.
- Final: fresh baseline, 30 iterations per run; checkpoint at 10, 15, 20, 25, 30. Target 5 independent runs per condition, with 3 acceptable if budget requires. Record the choice before final execution.
- Pair conditions on baseline/workload seeds; vary seeds across replicate pairs if desired and record them. Do not claim the model is deterministic because a workload seed is fixed.
- Alternate condition ordering and execute benchmarks serially. Keep pilot results separate from final analysis.
- Never stop final runs early merely because one condition appears better. Report actual incomplete horizons and causes.

Analysis outputs: per-operation latency, accepted-code normalized latency versus iteration, candidate correctness pass rate, request success rate, accepted-change count, repeated unsuccessful approaches under a documented classification rubric, and usage/cost where known. Show individual runs and uncertainty across runs; iterations are not independent replicates. With few runs, emphasize descriptive uncertainty over strong significance claims.

Define request success rate as `successful / total`, not successful/failed. Define comparative speedup as `stateless_latency / memory_latency` (greater than 1 favors memory), and baseline speedup as `initial_latency / current_latency`. Distinguish candidate measurements from retained-code measurements and missing values from zeros. Plot retained measured checkpoints without inventing results; independently remeasure final snapshots to check selection noise.

## Reproducibility and completion

Persist immutable baseline, config, dependency versions, CLI/model settings, source and prompt hashes, seeds, schemas, exact inputs, patches, tests, raw timings, audits, and accepted snapshots. Resume by journaled state and stable attempt IDs without duplicating completed steps or memory entries. Sanitize credentials and never commit secrets.

Completion means a documented command can run a mock experiment, an explicitly authorized live smoke experiment can complete, both conditions enforce isolation, interrupted execution resumes correctly, and analysis can reproduce figures from archived raw results. Real performance claims require real final-run data.

## Implementation reference

The official Codex iterative-loop example demonstrates separate role invocations and structured output: https://developers.openai.com/cookbook/examples/codex/build_iterative_repair_loops_with_codex . Check the installed CLI's supported arguments during integration; do not hard-code an assumed model or obsolete flags.

## Baseline protocol clarifications (2026-10-08)

The public v1 contract is `contracts/API.md`, with pinned validation examples in
`contracts/validation-errors.json`. Exact tags are case-sensitive, whitespace
trimmed, deduplicated by exact value, and sorted in Unicode string order. This
repairs the original implementation's undocumented case folding before baseline
freeze. Title/body limits are 1–200 / 1–5000 characters.

The milestone 2 harness uses real loopback HTTP and a new process/database for
each repetition. Runner-owned fixtures are seeded through the candidate API so
candidate schema/index changes survive. A fixed read-only warm-up leaves the
seeded logical state unchanged before timing. HTTPX timeouts currently bound
transport inactivity; whole-request/role execution budgets remain controller work.
Profiling captures endpoint functions in the server and worker threads, separately
from timing; it does not yet profile ASGI serialization or network overhead.

The inherited browser UI is preserved as ancillary functionality and excluded
from the objective. List/search remains an explicitly disclosed addition to the
proposal's four CRUD metrics. The proposal's successful/failed ratio and repeated
memory/memory formula are interpreted as successful/total and stateless/memory,
respectively, as defined above. Preserve raw counts for alternate presentations.
No final epsilon or experimental result is implied by baseline development checks.

## Implemented controller choices (2026-10-08)

Developer returns a schema-validated list of complete-file replacements/deletions.
The runner validates paths, preserves the public contract, and applies the patch
in a new candidate snapshot. All three role workspaces are read-only. This is a
stricter implementation of the role boundary and is identical across conditions.
Official tests run in the trusted process and exercise candidate HTTP subprocesses;
live evaluation additionally runs inside a network-disabled container.

Measurements alternate whole parent/candidate batch order by iteration. CLI mock
runs use real measurements; synthetic scores are confined to labeled unit fixtures.
Both conditions append factual records for all attempts, but only memory Planner
receives history. Memory is materialized from committed attempt records rather
than maintaining a separately mutable append log. Complete role results and
measurements are journaled; unresolved role calls are never silently repeated.

A run archives its full implementation, prompts, config, dependency/runtime
manifest, and content-addressed source snapshots. Resume rejects implementation,
configuration, or environment drift. The paired scheduler alternates condition
order and currently uses one recorded fixed workload seed across all replicate
pairs. It does not assume deterministic model output.

Analysis groups results by protocol, implementation, environment, phase, backend,
and synthetic/measured provenance. It reports descriptive uncertainty across
independent runs and explicitly identifies carried retained-code scores. Missing
usage/cost remain null. Repeated unsuccessful approaches use the same declared
approach category plus exactly matching case-folded, whitespace-normalized change
text after an earlier rejection; no semantic similarity claim is implied.

The real container boundary and baseline integration have passed unpaid checks.
Milestone 4's live inference check is still open. Final protocol configuration
must be frozen from completed real pilot evidence; final research execution is
not a side effect of implementation or a mock smoke command.
