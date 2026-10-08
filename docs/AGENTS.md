# Instructions for Codex Building This Research Project

## Scope

These instructions apply to the development repository. They are not the instructions for agents participating in the experiment. Never copy this file, SPEC.md, PLAN.md, or researcher notes into experimental workspaces.

Read SPEC.md and PLAN.md before implementing changes. SPEC.md defines intended behaviour and protocol; PLAN.md defines implementation order and completion checks. Follow explicit user instructions if they change scope, and record consequential protocol changes.

## Working process

- Implement the milestone requested by the user. If no milestone is specified for an implementation request, choose the first incomplete milestone. Do not proceed into another milestone unless the user requested broader work.
- Inspect existing code before editing; preserve unrelated changes.
- Make routine engineering decisions autonomously within the specification. Record material assumptions and surface unresolved questions that affect research validity.
- Use a mock backend before real model integration. Do not introduce a large agent framework unless necessary for a demonstrated requirement.
- Keep implementation readable, typed where useful, and modular at the application, measurement, controller, backend, and analysis boundaries.
- Do not optimize the deliberately inefficient baseline during setup.
- Add focused tests for actual correctness, measurement, isolation, rollback, and resume risks. Do not inflate test counts with tests that merely mirror code.
- Run the requested milestone's acceptance checks. Fix failures within scope, then update PLAN.md with actual commands, results, and remaining issues.
- Do not mark an unchecked live integration as completed based only on mocks.
- Summarize changes, validation, limitations, and the next milestone when finished.

## Research invariants

- Both conditions start from the same baseline and retain only accepted changes.
- Fresh role sessions every invocation; no resumed experimental conversation.
- Only the memory Planner receives the complete prior-attempt log. Stateless receives no prior attempts, conversation, or researcher logs.
- Use real isolation and allowlisted inputs; prompts alone are not access control.
- Keep base prompts, model settings, available tools, timeouts, and repair budgets identical between conditions.
- Log all attempts, including failed and rejected ones. Never remove inconvenient observations.
- The runner owns tests, raw measurements, acceptance decisions, and factual memory fields. Model prose cannot override them.
- Preserve complete memory without retrieval, filtering, compaction, or silent truncation.
- Protect the API contract, benchmark driver, workload, and official tests from experimental edits.
- Keep benchmark resets, warm-up, request sequence, and timing conditions identical. Profile separately from timed measurements.
- Do not allow benchmark-specific shortcuts, disabled persistence, altered endpoint semantics, or omitted slow/failing requests.
- Treat independent runs as experimental replicates; never treat iterations as independent samples.

## Files and configuration

- Use SPEC.md's suggested directory boundaries; document justified changes.
- Keep experiment artifacts and isolated runtime workspaces outside the experimental agents' accessible roots.
- Preserve baseline and accepted snapshots by content hash. Export clean code rather than exposing Git history.
- Put adjustable settings in versioned configuration; validate required final-run settings before execution.
- Pin dependencies and record CLI/model/runtime versions. Verify installed Codex flags instead of assuming support.
- Store secrets outside source control. Redact credentials from prompts, transcripts, commands, and manifests.
- Use schema-versioned JSON for machine interfaces and null for unavailable measurements.
- Write results atomically. Ensure recovery cannot duplicate memory entries or silently rerun completed paid calls.

## Verification and execution

Implement the target commands in PLAN.md and document exact setup in README.md. Run checks relevant to the current change rather than repeatedly running expensive experiments.

Mock calls and local correctness/measurement checks are normal implementation work. Live model calls and full experiment batches must be explicitly requested by the user or already covered by their current instruction; do not launch 30-iteration studies simply to test installation. Honor existing authorization without asking again for each normal step.

Never fabricate test results, latencies, token counts, costs, or experiment conclusions. Label synthetic fixtures and keep them separate from real data. Report blocked checks candidly with the exact missing prerequisite.

## Definition of milestone completion

A milestone is complete only when its implementation exists, required acceptance checks have passed, documentation describes how to reproduce them, and PLAN.md records the evidence. If a prerequisite prevents a check, leave that check open and explain the limitation.
