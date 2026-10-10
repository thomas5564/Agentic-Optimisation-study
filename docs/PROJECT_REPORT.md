# Experiment report and proposal alignment

Updated 2026-10-10. **Execution stopped at the user's request after completing the
active attempt.** The study contains one complete 30-attempt pair and one additional
memory attempt: 61 of the planned 300 final-study attempts. Seven scheduled runs
were not started. Software implementation is complete, but the proposed replicated
research study is incomplete. No further model calls are scheduled.

## Observed results: the one complete pair

| Measure | Stateless | Memory |
| --- | ---: | ---: |
| Completed attempts | 30 | 30 |
| Accepted changes | 1 | 2 |
| Correct candidates / evaluated candidates | 1 / 29 | 11 / 30 |
| Initial baseline score (ms) | 3.876690 | 3.855950 |
| Final independent score (ms) | 2.747079 | 0.995450 |
| Baseline / final speedup | 1.411× | 3.874× |
| Input tokens, all roles | 902,663 | 1,447,992 |
| Output tokens, all roles | 102,922 | 124,029 |
| Exact repeated unsuccessful approaches | 0 | 16 |

The final stateless/memory latency ratio is **2.760×** for this pair. This is a
descriptive observation, not evidence of a reliable causal memory benefit. There
is only one complete independent pair; uncertainty across replicate pairs cannot
be estimated. Memory's largest improvement occurred on its first attempt, before
any history existed, so that initial advantage cannot be attributed to memory.
The conditions also ran sequentially on one machine. The user-requested stop
occurred after interim results were visible; it was not a pre-registered stopping
rule, and no significance claim is made.

Stateless accepted attempt 4 (27.3% improvement relative to its measured parent),
reducing unnecessary internal object construction. Memory accepted attempt 1
(71.0%), moving filtering and pagination into SQLite while preserving literal,
case-sensitive matching, and attempt 14 (11.7% additional measured improvement).
Checkpoints at 10/15/20/25/30 and separate final remeasurements are archived for
both complete runs. Rejected candidates never became the next parent.

Stateless recorded 26 correctness failures, two syntax failures, one malformed
Planner output, and one evaluated correct candidate. Its malformed plan did not
produce an evaluated candidate, explaining the correctness denominator of 29.
Memory recorded 19 correctness failures and 11 evaluated correct candidates.
All attempts, including failed audits, remain in the evidence. The repeat count
uses the predeclared exact normalized change-text/category rule; it is not a
semantic measure of whether the model learned from failures.

The additional memory run completed one attempt before stopping. It is retained
as partial evidence, independently remeasured, and excluded from the complete-pair
comparison. The remaining horizon has not been extrapolated.

## Problem, inputs and outputs

The proposal asks whether complete prior-attempt memory helps an LLM optimize an
evolving application over a long horizon. Each attempt has a Planner, Developer,
protected correctness/performance evaluation, and Auditor. Both conditions retain
accepted code; only the memory Planner receives all previous attempt records.

Example application input: `POST /notes` with
`{"title":"Study","body":"Review SQLite","tags":["course"]}`.
The expected output is HTTP 201 with the same fields plus a generated integer
`id`. A later `GET /notes/{id}` must return the persisted note. Optimization must
preserve this behavior, Unicode, error bodies, case-sensitive search/tag matching,
pagination, SQL parameterization, and persistence after restart.

An optimization input consists of current source, the public API contract,
profile evidence, and (only for memory Planner) prior outcomes. The Developer's
output is a schema-validated complete-file patch. The runner accepts it only if
correctness passes and measured latency improves by more than the frozen 8%.

## Dataset and measurement

The dataset is synthetic and reproducible, not an external text corpus: 2,000
initial notes from seed 7, five title prefixes, Unicode body content, and one or
two unique tags selected from seven. Each 12-request cycle contains one Add,
three Get, one Update, one Delete, and six List/Search operations, including reads
after mutations. Each measurement uses 100 cycles per repetition and five
repetitions: **6,000 timed requests per snapshot**. Concurrency is one.

Each repetition starts a fresh process and database, seeds through the candidate
API, verifies the fixture, and performs two fixed read-only warmup cycles before
timing. A reference-state oracle checks response semantics. The primary score is
the median of five repetition means; per-operation means/p95 and raw requests are
also exported. Seeding, warmups, profiling and oracle work are excluded from request
latency. Profiling runs separately and covers endpoint work rather than all ASGI
or network overhead. Benchmarks execute serially in network-disabled containers.

The unchanged baseline's pilot relative ranges were 2.404% and 3.916%. The
pre-recorded rule selected epsilon 8%. Model/provider, prompts, workload, budgets,
timeouts and five-pair replication target were frozen before final outcomes in
`configs/final.yaml` and `configs/final.protocol.json`. Frozen config hash:
`463cd34538d57637df7d85be20f119f0648e63ce3fe421ed473716371969ec54`.

## Pilot and provider compatibility

Both fresh Chat pilots completed ten attempts. Stateless had zero correct or
accepted candidates; memory had one correct candidate, whose 1.53% improvement
was below threshold, and no accepted changes. The original baseline was retained
in both. Pilot input/output tokens were 297,502/41,897 for stateless and
332,062/24,840 for memory. One stateless audit exhausted the output budget.
Pilot data is separate from final-study data.

The supplied `soclaas.env` is ignored by Git and parsed as data, never executed.
The active backend sends fresh Chat Completions requests with native strict JSON
schemas, client-side validation, `tool_choice=none`, temperature 0.2, and a
12,000-token output limit. No reasoning parameter is sent. The configured model is
`default`; all 179 responses in the complete final pair reported `qwen3.6:35b`.
This provider alias/name is not an immutable weight version. Pricing was not
reported, so dollar cost remains unknown.

The original Codex CLI route could not use nested sandbox namespaces. An initial
Responses pilot then encountered provider-internal tool errors and was halted.
Its eight completed attempts and unresolved ninth attempt are preserved as a
separate diagnostic cohort. Neither failed route is pooled with the Chat study.
No sandbox was disabled to bypass the CLI limitation.

Calibration also corrected the harness listener's TCP_NODELAY setting to remove
approximately 40 ms of transport overhead. Application baseline source was not
changed. Earlier socket timings and a noisy 500-note calibration are separate
from the final 2,000-note protocol.

## Integrity, verification and proposal alignment

The complete memory run's Planner input counts were exactly 0 through 29;
stateless counts were all zero. Developer and Auditor had no direct prior-attempt
history. No history was filtered, summarized or truncated. Input admission limits
are conservative byte limits, not measured token counts. Current source and the
public contract are explicit model inputs; host files, researcher documents and
run archives are not exposed as tools. Candidate evaluation has no network or
credentials. The runner controls tests, measurements and acceptance.

| Proposal requirement | Delivered treatment |
| --- | --- |
| Persistent notes CRUD application | Immutable correct baseline; list/search disclosed as an extension |
| Planner / Developer / Auditor | Fresh live role requests with structured outputs |
| Full continuously accumulating memory | All prior attempts delivered only to memory Planner |
| Otherwise identical conditions | Same source retention, model, prompts, tools, budgets and workload |
| Correctness and latency evidence | Protected tests, oracle, per-operation/raw measurements |
| 30 iterations; checkpoints 10/15/20/25/30 | Completed for one pair; additional run stopped after one attempt |
| Replicated comparison | Five pairs planned; only one complete pair, so research completion remains open |

The proposal's successful/failed ratio is reported as successful/total, retaining
raw counts. Its repeated memory/memory formula is interpreted as stateless/memory
speedup. These clarifications were recorded before execution. The structured-patch
Developer and direct API backend are documented implementation choices applied
identically to both conditions.

The full automated suite passed 100 tests (33 existing deprecation warnings);
the full suite was rerun after the final request-format change and again passed
all 100 tests in 15.67 seconds. Real container readiness, baseline correctness, isolation, mock failure
paths and interrupted-state recovery were also verified. Final wrap-up checks
are recorded in `research/evidence/live-2026-10-10/wrap-up-verification.json`.

## Evidence and reproducibility

The permanent external artifact root is
`/Users/jaymesonkoh/.codex/visualizations/2026/10/09/01a11e69-8712-76f2-a79c-5dacf01d710e/experiments/`.

- `soclaas-final-2026-10-10/`: exact role inputs/outputs, patches, source snapshots,
  raw timings, journals, manifests, checkpoints and explicit user-stop record.
- `soclaas-final-report-2026-10-10/`: offline HTML, figures and CSVs, including the
  explicitly incomplete additional run; paired comparison uses complete pairs only.
- `soclaas-chat-pilot-2026-10-10/` and `soclaas-chat-pilot-report-2026-10-10/`:
  separate completed paired pilots and analysis.
- Repository `research/evidence/live-2026-10-10/`: compact execution, integrity and
  verification records. The frozen baseline remains in `research/baseline/`.

Regenerate the base analysis without model calls using
`python -m analysis.report --runs-dir <final-run-root> --output <new-report-root>`.
The presentation layer and complete-pair-only figures can then be reproduced
with `PYTHONPATH=. python research/evidence/live-2026-10-10/render-wrap-up.py`
on this machine. Do not overwrite the frozen protocol or pool diagnostic, pilot
and final cohorts.
The updated eight-minute presentation is
`output/presentations/memory-guided-optimization-updated-8min-2026-10-10.pptx`.
It covers the input/output example, frozen dataset, live progress and preliminary
complete-pair results, with timed speaker notes and explicit replication limits.
The older presentation remains available as historical pre-experiment progress.
