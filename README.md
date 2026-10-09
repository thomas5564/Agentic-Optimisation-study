# Memory-Guided Long-Horizon Code Optimization

A COMP 690-158 research testbed comparing stateless and full-history LLM code
optimization. The corrected notes baseline and local benchmark/profile harness
are implemented, together with the mock controller, memory treatment, resume,
replication, analysis, and container backend. Unpaid container checks pass; the
live-model smoke check and research experiments remain to be run.
See [the current report](docs/PROJECT_REPORT.md), [specification](docs/SPEC.md),
and [implementation plan](docs/PLAN.md). Read [development instructions](docs/AGENTS.md)
before making changes; those instructions are never experimental agent inputs.

## Setup

Verified with Python 3.13.2 on macOS arm64. Python 3.11+ is declared; other
platforms/versions have not been verified. Keep the runtime fixed within a study.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
python -m pip check
```

`requirements.lock` pins all measured runtime/test dependencies. Editable
installation uses setuptools; build tooling is not part of timed execution.
The app's existing startup hook and the pinned TestClient emit deprecation
warnings; these do not invalidate the passing checks.

## Run the API and correctness checks

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python -m pytest tests/ -q
```

The app uses `notes.db` unless `NOTES_DB_PATH` is supplied. Existing browser UI is
available at `/`; only API operations enter the benchmark. Public behavior and
representative exact validation errors are frozen in [contracts](contracts/API.md).
Tags and substring searches are case-sensitive.

## Measure and profile

Use a fresh output directory for each command; existing result files are not
overwritten. These commands open temporary loopback HTTP servers. A restricted
execution environment may require permission to bind to localhost.

```bash
python -m benchmarks.run --config configs/pilot.yaml --output /tmp/notes-benchmark
python -m benchmarks.profile --config configs/pilot.yaml --output /tmp/notes-profile
```

`--app-root /path/to/candidate` measures another root containing `app/main.py`.
The trusted harness seeds through the candidate's HTTP API, allowing alternative
schemas and indexes. It never drops tables or uses the developer's `notes.db`.
Every repetition starts a new process and a new temporary database, verifies the
logical fixture, runs a fixed read-only warm-up, then measures the same trace.
Read-only warm-up leaves the original fixture unchanged. A host/user-wide lock
serializes benchmark/profile commands. Concurrency is fixed at one.

The development config uses 100 seeded notes, 20 cycles of 12 requests, two
warm-up cycles, and five timing repetitions. A cycle exercises add, get, update,
delete, list/search, and reads after mutation. Generated IDs are explicit request
dependencies. Latencies use a monotonic clock and exclude oracle checks, seeding,
warm-up, and profiling. End-to-end workload elapsed time also includes driver and
oracle overhead and is reported separately. HTTPX's configured timeout applies to
connect/read/write/pool inactivity, not a universal wall-clock execution limit.

`benchmark_summary.json` contains raw request results, per-operation mean/p95,
counts, all repetition means, environment/dependency versions, code/config/trace
hashes, and noise. p95 uses nearest rank. The primary score is the median of
repetition means. Any failed response, timeout, missing dependency, fixture,
startup, or warm-up failure invalidates the score (`null`). Diagnostics retain
observed failure latencies; they are not acceptance scores. Exit status is nonzero
for an invalid measurement. The harness reports official tests as `null` because
the future controller must run the protected suite separately.

Profiling emits `application.prof`, `profile.txt`, and `profile_summary.json`.
It captures endpoint function work, including synchronous worker threads, while
excluding seeding/warm-up. It does not cover ASGI serialization/network overhead.
Profile scores are always null and are never used for acceptance.

These processes are local measurement workers, **not security sandboxes**.
Use the container-backed controller for live output; the standalone local
benchmark and local mock evaluator are not security boundaries.

## Baseline and evidence

The preserved baseline is `research/baseline/source.zip`; its content manifest is
`research/baseline/manifest.json`. Only app files and sanitized contracts are in
the archive—no history, researcher notes, tests, or benchmark driver. To create a
new explicitly chosen baseline in a new destination:

```bash
python -m benchmarks.snapshot --output /path/to/new-baseline
```

Do not replace the existing baseline. Development measurement/profile evidence is
under `research/evidence/`. This is baseline verification, not a model pilot or
condition comparison. Old tracked `tmp/` and `benchmark-output/` results predate
the corrected harness and contain semantic failures; they are not valid evidence
of optimization gains.

Next execution step: an explicitly requested live smoke iteration with a chosen
model. No real model calls or long-horizon research experiments have run.

## Optimization controller, memory, and resume

Milestones 3, 5, and 6 are implemented and tested. Milestone 4's container adapter
and unpaid integration checks pass; a live model iteration remains unchecked.
The pipeline profiles the accepted snapshot, invokes three fresh roles, validates
a JSON patch, runs protected correctness tests and measurements, makes a
deterministic acceptance decision, and atomically records the attempt and memory.
Developer submits complete file replacements; all agent workspace mounts are
read-only. The runner alone applies allowed app edits. Explicit SQLite durability
disabling is rejected; public behavior/persistence is tested separately over HTTP.

```bash
python -m controller.run --backend mock --condition stateless --iterations 1 --config configs/smoke.yaml --output /tmp/notes-mock
python -m controller.batch --backend mock --iterations 3 --config configs/mock-paired.yaml --output /tmp/notes-mock-paired
python -m controller.resume --run-dir /tmp/notes-mock-paired/pair-00-memory
```

Run destinations must be outside this development checkout. `mock-paired.yaml`
runs one replicate pair for smoke verification; this is not statistical evidence.
Both conditions retain accepted changes. Only the memory Planner receives exactly
all preceding attempt entries. Developer sees the current plan; Auditor sees the
current patch, validation, measurements, and runner decision. Roles share the same
base prompts, model settings, tool/timeout/output limits, and zero repair/retry
budget. The sole intentional history difference is the Planner's memory payload.

Mock backend outputs are fixtures. Its CLI still runs real correctness tests,
profiles, and timings. Synthetic timings exist only in controller tests and are
explicitly labeled. Smoke epsilon is a control-flow setting, not a final calibrated
threshold. Parent/candidate measurement batch order alternates by iteration.
Rejections, syntax failures, malformed role output, no-ops, and role timeouts count
as attempts. Infrastructure failures pause the same iteration with archived evidence.

Each run retains `manifest.json`, a complete runner-source archive, immutable
content-addressed snapshots, exact role inputs/outputs, raw measurements, patches,
per-attempt records, checkpoints, and `memory.json`. Attempt records are the source
of truth; memory is regenerated idempotently to prevent duplicate appends.
Completed role calls and measurements are reused on resume. Runner/test/prompt,
configuration, environment, and snapshot drift stop resume instead of silently
changing the protocol. Restore the recorded implementation from `runner-source.json`
in a separate checkout when resuming an older run.

A crash while a role call is in progress has an unknown outcome. Resume stops
without repeating that call. Inspect its artifact directory, then choose one:

```bash
python -m controller.resume --run-dir /path/to/run --recover-call 001-developer
python -m controller.resume --run-dir /path/to/run --abandon-call 001-developer
```

Recovery requires a complete saved `result.json`; abandoning records an explicit
unknown/failed outcome. Neither command issues that role call again. Context
budgets apply to the complete input and source; no history is compacted or removed.
An overflow or observed CLI compaction stops the run with `context_limit`. Input
byte budgets are conservative admission checks, not measured token counts.

## Isolated Codex backend

The container recipe has a minimal build context: CLI plus pinned dependencies,
with no project, credentials, or session history baked into the image. The version
below was verified locally; inspect a chosen CLI version rather than guessing flags.

```bash
docker build --build-arg CODEX_VERSION=0.162.0-alpha.2 -t notes-experiment:dev containers
docker image inspect notes-experiment:dev --format '{{.Id}}'
python -m agents.preflight --config configs/isolation-check.yaml
python -m controller.check_environment --config configs/isolation-check.yaml --output /tmp/notes-container-check
```

Set the resulting immutable image ID in a copied config. `isolation-check.yaml`
records the locally tested image; another machine must have that exact image or
record its own build ID. The preflight is unpaid: it checks CLI capabilities and
actual mount permissions with a host-history sentinel. `check_environment` also
runs the baseline correctness suite, benchmark, and profiler in the container.

Every role gets a new container, read-only app/contract and schema mounts, a fresh
output directory, and ephemeral home/session state. No developer home, Git,
researcher logs, other runs, tests, or Docker socket is mounted for an agent. The
container has a read-only root, dropped capabilities, resource limits, and no
privilege escalation. Candidate evaluation runs in separate network-disabled
containers without credentials; tests talk to separate HTTP server processes.
Agent containers need outbound access for inference and use the CLI's read-only
tool sandbox. The default bridge network is not an API-domain egress allowlist;
use a controlled network/proxy if the study environment exposes private services.

For an explicitly requested live smoke run, copy `configs/live.example.yaml`,
choose a model and image ID, and supply `CODEX_API_KEY` through the environment
outside source control. The adapter never mounts or reads the host login directory.
It redacts keys/bearer credentials from archived output, uses no resumed sessions,
and captures supported usage fields; unknown usage/cost stays null.

```bash
python -m controller.run --backend codex --condition stateless --iterations 1 --config /path/to/live.yaml --output /tmp/notes-live-smoke
```

No live inference has been run or certified. API authentication, model availability,
actual role behavior, and live context/compaction behavior remain to be checked.

## Offline analysis and final protocol

```bash
python -m pip install -r requirements-analysis.lock
python -m analysis.report --runs-dir /tmp/notes-mock-paired --output /tmp/notes-report
```

The HTML report includes latency, candidate correctness, and request-success PNGs.
CSV exports cover attempts, requests, repetitions, per-operation means/p95,
checkpoints, run-level correctness/acceptance counts, repeated unsuccessful
approaches, and available usage/cost. Separate cohorts prevent pooling different
protocols, phases, backends, or synthetic/measured data. Missing values stay null
or blank. Incomplete runs are not extrapolated. Retained-code curves explicitly
carry the last measured value until a new measurement exists; final snapshots and
configured checkpoints are independently remeasured. Uncertainty is descriptive
sample SD/range across independent runs, never across iterations. Exact normalized
change text plus approach category is the documented repeat-classification rubric.

After explicitly requested live pilots of both conditions, freeze a chosen final
config before observing final outcomes:

```bash
python -m controller.freeze --config /path/to/chosen-pilot-settings.yaml --pilot-runs /path/to/stateless-pilot /path/to/memory-pilot --output configs/final.yaml
python -m controller.batch --backend codex --iterations 30 --config configs/final.yaml --output /path/to/final-runs
```

Freezing requires real completed pilot evidence, unchanged model/image/workload
settings, epsilon above the observed baseline relative-range noise, an explicit
context admission limit, and at least three replicate pairs. The final horizon
is exactly 30, with checkpoints at 10/15/20/25/30. Batch order alternates conditions
across pairs, uses the same recorded workload seed within and across pairs, and
serializes all measurement. Final run data and figures do not yet exist.
