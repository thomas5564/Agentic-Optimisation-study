# Project status and proposal alignment

Updated 2026-10-08 after completing the remaining software implementation and its
mock/unpaid integration checks. The original proposal's research design remains
intact. There are no live-model results or claims that memory improves performance.

## Milestone status

| Milestone | Status | Evidence |
| --- | --- | --- |
| 1: Correct baseline | Complete | API contract, pinned runtime, immutable source archive, persistence/semantic tests |
| 2: Measurement/profile harness | Complete | Real HTTP, deterministic fixtures, oracle, resets/warm-ups, raw metrics, independent endpoint profiling |
| 3: Mock iteration | Complete | Typed role schemas, patch validation, protected evaluation, deterministic acceptance, exact rollback, factual records |
| 4: Codex backend | Implemented; live iteration open | Actual CLI flags checked; image built; real container boundary and baseline integration passed; no paid call |
| 5: Memory/long horizon | Implemented and mock-verified | Three iterations per condition; complete ordered history only reaches memory Planner; context limits stop explicitly |
| 6: Resume/replication/analysis | Complete as software | Crash-recovery tests, idempotent memory, paired schedules, checkpoints/final remeasurement, offline figures/CSV |
| Research execution | Not started | Live smoke, model pilots, final protocol freeze, and 30-iteration study remain open |

Milestone 4 is deliberately not marked fully complete because its live integration
acceptance check has not run. Software completion is distinct from producing the
proposal's research findings.

## What was implemented in this continuation

The controller exports clean accepted snapshots to fresh role workspaces. Planner
receives the current profile; Developer returns a typed complete-file patch;
the runner applies allowlisted app edits, checks correctness, and measures parent
and candidate with alternating batch order. Only a valid improvement greater
than epsilon is accepted. Auditor interpretation cannot change any factual
measurement or acceptance decision. Failed, rejected, malformed, timed-out, and
no-op attempts remain in the record. Infrastructure failures pause the same iteration.

Every role workspace contains only current app and public contract. Role mounts
are read-only; the runner applies Developer's structured output. Live roles use
fresh containers and ephemeral Codex homes, never resumed conversations. Evaluator
containers have no network or credentials; the protected official tests talk to
separate candidate HTTP processes instead of importing candidate code into pytest.
The host project, Git, researcher notes, sibling runs, and prior sessions are not
mounted for agents. Explicit disabling of SQLite durability is also rejected.

Both conditions retain accepted code. At iteration k, memory Planner receives
exactly k−1 complete prior-attempt entries; stateless receives none. Developer and
Auditor receive no direct history. Memory is serialized deterministically, with
entry counts and hashes, and is never retrieved selectively or summarized.
Input admission limits are conservative byte checks, not measured token usage.
An overflow or detected CLI compaction ends the run explicitly.

Each run archives its configuration, environment, full runner source, prompts,
content-addressed snapshots, exact role inputs/outputs, patches, raw timings,
attempt records, and checkpoint/final measurements. Atomic journals hash completed
results. Attempt records are authoritative; memory is materialized from them,
preventing duplicate append after interruption. Unknown role-call outcomes require
explicit saved-result recovery or abandonment, never an automatic repeated call.

Batch scheduling alternates condition order by replicate pair while sharing the
recorded workload seed. Analysis exports attempts, requests, repetitions,
per-operation latency, checkpoints, correctness/acceptance counts, repeat-family
classification, and available usage/cost. It separates protocol, implementation,
environment, phase, backend, and synthetic/measured cohorts. Uncertainty is across
independent runs; unavailable values stay null. Figures clearly label mock data
and carried measurements. Final configuration freezing is gated on completed real
pilot evidence from both conditions and an epsilon above observed baseline noise.

## Actual verification

- `.venv/bin/python -m pytest tests/ -q`: **92 passed**, 33 existing deprecation
  warnings, 15.27 seconds. Tests include all mock failure/acceptance cases,
  interrupted commit boundaries, unresolved/recoverable calls, memory routing,
  context overflow, schema/path attacks, real candidate correctness failure,
  paired order, duplicate-run detection, and missing/all-failed analysis fixtures.
- `.venv/bin/python -m controller.batch --backend mock --iterations 3 --config configs/mock-paired.yaml --output /tmp/notes-mock-verified-2026-10-08`:
  both conditions completed three attempts with real measurement. Both recorded
  a rejected comment-only change, a syntax failure, and a no-op. The baseline
  remained unchanged; no optimization gain is claimed.
- Planner memory counts were **0,0,0** for stateless and **0,1,2** for memory.
  Developer/Auditor inputs had no prior-attempt entries.
- `.venv/bin/python -m controller.resume --run-dir /tmp/notes-mock-verified-2026-10-08/pair-00-memory`:
  completed successfully; hashes of every archived JSON file were unchanged.
- Docker **29.6.1**, host/container Codex CLI **0.162.0-alpha.2**. The minimal
  image was built and its immutable ID recorded in `configs/isolation-check.yaml`:
  `sha256:385b5ef7719da065679daedf775a6a35567c9be0ddffa3143e659f21ab744238`.
- `agents.preflight`: actual host/sibling sentinel, fresh-history, and read-only
  app/contract/schema checks passed, with only the new output directory writable.
- `controller.check_environment`: protected baseline tests, **48/48 valid timed
  requests**, and endpoint profiling passed inside the container, with **zero live
  model calls**. Container runtime: Python 3.13.16, Linux aarch64, SQLite 3.40.1.
- `analysis.report` regenerated CSV/HTML/PNG artifacts entirely offline. The plots
  were visually inspected and mark mock results explicitly.
- `pip check` and `git diff --check` passed.

[Verification manifest](../research/evidence/controller-2026-10-08/verification.json)
records the exact external run/report paths and source hashes. Research runs remain
outside the development checkout; researcher summaries are never agent inputs.
Earlier development runs were retained rather than overwritten.

The original milestone 2 macOS baseline measurement still stands as historical
setup evidence: five repetitions, 1,200 valid requests, score 1.109207 ms, sample
CV 16.07%, relative range 34.48%. It is not directly comparable to container timings.
The standalone benchmark and local mock evaluator are not security sandboxes.

## Proposal alignment and deliberate choices

| Proposal requirement | Current treatment |
| --- | --- |
| Persistent notes CRUD application with realistic optimization opportunities | Preserved, verified baseline; not optimized during controller construction |
| Planner, Developer, Auditor | Typed fresh invocations; mock implemented; Codex adapter built, actual inference pending |
| Full continuously accumulating memory | All accepted/rejected/failed attempt entries go only to memory Planner |
| Otherwise identical stateless process | Same pipeline, base prompts, model/config, tools, budgets, and accepted-code retention |
| Compilation/correctness plus Add/Update/Delete/Get timings and counts | Runner-owned syntax/startup/tests plus separate CRUD measurements and raw failure counts |
| Fixed workload and profile feedback | Runner-owned deterministic seed/trace/oracle, serial measurements, separate profiling |
| Up to 30 iterations, checkpoints every five from 10 | Implemented horizon/checkpoints at 10/15/20/25/30; final runs require exactly 30 |
| Compare trajectories and overall condition performance | Offline run-level analysis implemented; real final data still required |

Developer's read-only workspace plus structured patch output is a stricter,
reviewable implementation of the proposed implementation role, applied identically
to both conditions. The existing browser UI remains ancillary. List/search is
reported as an explicit extension to the proposal's four CRUD operations.

The proposal's successful/failed ratio is undefined when failures are zero; use
successful/total while retaining raw counts. Its final memory/memory runtime
formula is interpreted as stateless/memory speedup. These prior documented
clarifications remain unchanged. Repeat classification is deliberately conservative:
same approach category plus exact case-folded, whitespace-normalized change text
after a rejection; it does not claim semantic equivalence between different plans.

## Remaining checks and execution work

1. Choose an explicit model and supply CODEX_API_KEY outside source control, then
   explicitly request/run one live smoke iteration. Authentication, actual role
   behavior, model usage reporting, and live compaction handling remain unverified.
2. Run authorized live pilots, inspect optimization headroom, workload length,
   runtime/cost, and noise on the chosen fixed execution environment. Smoke epsilon
   is not a final threshold. The default agent bridge network permits inference but
   is not an API-domain egress allowlist; use controlled egress where private services
   are exposed. Candidate evaluation itself has no network.
3. Freeze the final protocol from real paired pilot evidence, then run the agreed
   independent replicate pairs for the full 30-iteration horizon and produce the
   proposal's research conclusions from those observations.

The code does not certify arbitrary candidate programs against every possible
benchmark shortcut; path restrictions, durability checks, external correctness
checks, deterministic response validation, and the archived patch/audit provide
complementary evidence. Real model behavior and final comparisons still require
review during the live smoke/pilot stage.
