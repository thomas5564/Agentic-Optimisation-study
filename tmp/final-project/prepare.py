from pathlib import Path
import json,shutil
root=Path.cwd(); out=root/'output/report'
# Keep the existing October report intact as historical evidence.
old=root/'docs/PROJECT_REPORT.md'; arch=root/'docs/PROJECT_REPORT_2026-10-11.md'
if not arch.exists(): shutil.copyfile(old,arch)
f=json.loads((root/'tmp/final-project/facts.json').read_text())
strict=f['strict']; unc=f['unconstrained']
text='''# Memory-Guided Long-Horizon Code Optimization: final project report

Updated 2026-11-18. This report supersedes the October progress summary, preserved in
[the historical report](PROJECT_REPORT_2026-10-11.md). It incorporates the README's
November testbed-v2 studies and checks their summaries against recorded attempts.
No new model calls or experiment runs were needed for this update.

## Status and principal finding

The software implements a persistent notes app, protected evaluation, fresh
Planner/Developer/Auditor calls, rollback, full-history memory, bounded LRU memory,
resume, and offline analysis. Two exploratory v2 studies each completed 30 attempts
for each of three arms (180 attempts total). Each study has **one independent run
per arm**, executed in the order LRU, full memory, stateless. These are descriptive
comparisons, not replicated estimates of a causal memory effect.

With the strict scope rule, final latency was 0.737 ms without history, 0.584 ms
with full history, and 0.560 ms with LRU. LRU consumed 18.7% fewer input tokens than
full history. The 4.3% full-history/LRU latency ratio does not establish equivalence,
and is smaller than the per-change 8% acceptance threshold; that threshold is not a
confidence interval. The unrestricted study produced little separation because
all arms bundled most improvements into their first patch.

## Problem definition

**Input:** the current FastAPI/SQLite notes-app source, public API contract,
current profile and timing evidence, plus the arm's allowed prior-attempt records.
For example, a profile can show that reading a single note scans all 2,000 notes.

**Output:** a schema-validated patch containing replacement app files; the runner
retains it only if protected checks pass and latency improves by more than 8%
relative to its measured parent. An example candidate replaces a full-table scan
with a parameterized ID lookup. This is an illustrative transformation, not a
claim that every generated patch behaves correctly.

Application example: `POST /notes` with
`{"title":"Study","body":"Review chapter 2","tags":["course"]}` returns HTTP 201,
the same fields, and a generated integer ID; later reads must return the persisted
note. Unicode, exact error bodies, case-sensitive matching, pagination and
persistence remain required. Passing the present tests is weaker than proving the
entire API contract (see limitations).

## Related work

PerfAgent (Deng et al., 2026, https://arxiv.org/abs/2607.19653) motivates using
profiling and verification for iterative repository optimization. Reflexion
(Shinn et al., 2023, https://arxiv.org/abs/2303.11366) retains linguistic feedback
across trials. Self-Refine (Madaan et al., 2023,
https://arxiv.org/abs/2303.17651) iteratively refines outputs using self-feedback.
Our controller is a custom implementation: it compares Planner history policies
while retaining accepted source in every arm, and makes acceptance a runner-owned
decision rather than a model judgment.

## Dataset and annotated examples

The dataset is generated within this project (`benchmarks/fixtures.py`), not an
external corpus or an LLM training dataset. Seed 7 generates 2,000 starting notes:
400 for each of five title prefixes; Unicode bodies; 1–2 distinct tags drawn from
seven values. There is one application task and two baseline versions, not 2,000
independent optimization tasks.

Exact first generated record:

```json
{"title":"Beta #1","body":"Deterministic note 1. Unicode: café 世界. seed=7","tags":["alpha","notes"]}
```

- `title`: one repeated prefix plus a unique index; exercises list/search.
- `body`: includes non-ASCII content; exercises round-trip preservation.
- `tags`: two values here; exercises exact tag filtering.

A test trace uses the records through the HTTP API. Each 12-request cycle has
one Add, three Get, one Update, one Delete and six List/Search requests. There
are 100 cycles per repetition and five repetitions, giving 1,200 requests per
repetition and 6,000 timed requests per snapshot. Fresh processes and databases,
two read-only warmup cycles and a reference-state oracle make inputs repeatable.
Concurrency is one; fixture generation, warmup, oracle work and profiling are
outside request timing.

**Train/development/test split:** not applicable to model training: no weights are
updated and there are no training examples. The development config uses 100 notes
and 20 cycles. The reported study workload uses 2,000 notes and 100 cycles. It is
repeated optimization feedback, not a held-out test split. No unseen workload,
seed or application was evaluated, so workload overfitting remains possible.

## Method and baselines

**Key insight:** A record of earlier attempts may prevent repeated mistakes, but
keeping every entry increases context cost and can preserve obsolete advice.
A bounded notebook tests whether selective retention is enough.

**Overview:** Profile the current retained app. A fresh Planner proposes a change,
and a fresh Developer returns replacement app files. The protected runner validates,
tests and measures the candidate, retaining it only on sufficient improvement.
A fresh Auditor interprets the result, after which the runner records factual
outcomes and updates the allowed Planner memory.

All arms retain accepted code. Stateless receives no attempt history; full memory
receives every preceding attempt without truncation; LRU receives at most six
entries. Only the Planner directly receives history. Developer sees the current
plan; Auditor sees the current patch, checks, measurements and runner decision.
Thus the baseline is history-free reasoning over an evolving program, not a reset
to the original code at every iteration.

For LRU, the Planner returns `used_memory` iteration IDs. Valid citations to shown
entries refresh their recency, then the new entry (including failures) is inserted
and the least recently used entries are evicted until six remain. Invalid citations
are ignored and logged. Entries are presented in chronological order; recency is
used for eviction. Citations are self-reports, not proof of causal use. All attempts
remain in the archive even when absent from the Planner's cache.

Testbed v2 changes `app/db.py` to distribute avoidable work across operations:
repeated scans, Python filtering/pagination, repeated row validation, connection
setup, and deletion-time VACUUM. Routes, data generator, workload and protected
checks remain unchanged. Researcher-written reference fixes are calibration tools
and are never shown to agents. Host calibration measured about 7.7× headroom;
it is not a universal lower bound or directly comparable to container times.

The November 12 study has a prose request for one focused optimization but no
runner-enforced operation limit. In the November 13 study, the runner rejects
patches changing more than one public data-operation definition before evaluation.
Private helpers and module-level code may change freely; this syntactic rule is
not proof that a patch affects only one operation semantically. Both Planner and
Developer receive the strict instruction equally across arms. LRU and strict scope
are explicit extensions to the original full-history proposal, not replacements
for the original treatment.

## Experimental setup and metrics

Each v2 study uses SOCLAAS Chat Completions, reported model `qwen3.6:35b`, temperature
0.2, 12,000 maximum response tokens, no model tools, no repairs or retries, and
30 attempts per arm. The provider alias is `default`, not an immutable weight ID.
Config phase `smoke` is a controller compatibility label; these are separate
exploratory three-arm studies, not the original frozen two-arm final protocol.

- **Latency score:** median of the five repetition means, in milliseconds/request;
  lower is better. A final independent remeasurement supplies final table values.
- **Acceptance:** correctness passes and `(parent − candidate) / parent > 0.08`.
  Rejected candidates do not become the next parent. The 8% rule is a decision
  threshold calibrated above original pilot variation, not a significance test.
- **Speedup:** the arm's initial latency divided by its final independent latency.
- **Convergence:** first iteration after which every recorded retained latency is
  at most 1.05 times the last retained latency. It is retrospective; the last
  retained score can differ from the independent final remeasurement.
- **Error rate:** test/syntax/patch failures plus malformed output/timeouts divided
  by all 30 attempts. No-ops, correct-but-too-small changes and scope rejections
  are distinct categories. No scope rejections occurred in these recorded studies.
- **Input tokens:** sum of reported input tokens across all roles and 30 attempts;
  not wall-clock time or dollar cost. Provider pricing is unavailable.

## Experiment 1: absence of enforced scope

**Research question:** Does unrestricted patch scope leave enough sequential
optimization work to distinguish memory policies?

Rows below are arms. Columns are independent final remeasurement latency, accepted
patch count and aggregate input tokens; lower latency/tokens are preferable.

| Arm | Final latency (ms) | Accepted | Input tokens |
| --- | ---: | ---: | ---: |
'''
for arm,label in [('stateless','Stateless'),('memory','Full history'),('memory_lru','LRU, K=6')]:
 r=unc[arm]['report'];text+=f"| {label} | {r['final_remeasurement_score_ms']:.3f} | {r['accepted_changes']} | {r['input_tokens']:,} |\n"
text+='''
All arms rewrote several data operations on attempt 1, which captured 83–98% of
the total gain measured in speedup multiples. Final latencies differ by about 9%
across arms. **Conclusion:** this single-run design poorly exposes long-horizon
memory effects; it motivated the enforced rule. It does not demonstrate that
memory is generally useless or that the arms are equivalent.

## Experiment 2: enforced scope

**Research question:** When patches are limited syntactically to one public data
operation, how do memory policies differ in retained latency and search behavior?

Rows are arms; columns report independent final latency, own-baseline speedup,
accepted changes, errors/all attempts, no-ops and convergence iteration. Error
rate and no-op count must be read together; more accepted steps need not mean a
better final program.

| Arm | Final ms | Speedup | Accepted | Errors | No-ops | Convergence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
'''
for arm,label in [('stateless','Stateless'),('memory','Full history'),('memory_lru','LRU, K=6')]:
 a=strict[arm];r=a['report'];c=a['outcome_counts'];errs=c.get('tests failed',0)+c.get('malformed',0)
 text+=f"| {label} | {r['final_remeasurement_score_ms']:.3f} | {r['baseline_speedup']:.2f}× | {r['accepted_changes']} | {errs}/30 | {c.get('noop',0)} | {a['converged_iteration']} |\n"
text+='''
Stateless stalled on `list_notes` during attempts 4–15 and never fixed
`create_note`. Both memory arms reached all five operation fixes by about iteration
6. Full history later accepted another change at 21; LRU accepted only attempts
1–5 and then produced 20 no-ops. **Conclusion:** the two history arms finished
with lower latency in this run, while LRU progressed earlier. One trajectory per
arm cannot establish a general causal advantage; the low LRU error rate partly
reflects inactivity, not uniformly better proposals.

## Experiment 3: memory cost and capacity

**Research question:** Can six-entry LRU preserve similar observed speed while
reducing input context compared with complete history?

Rows are the strict-study arms. Columns are total input tokens and maximum
observed Planner input tokens (a different quantity from all-role totals).

| Arm | Total input tokens | Max Planner input tokens |
| --- | ---: | ---: |
'''
for arm,label in [('stateless','Stateless'),('memory','Full history'),('memory_lru','LRU, K=6')]:
 a=strict[arm];text+=f"| {label} | {a['input_tokens']:,} | {max(a['planner_tokens']):,} |\n"
text+='''
LRU used 1,060,182 versus 1,304,740 full-history input tokens, an 18.7% reduction.
Its final latency was 4.1% lower, a descriptive gap that cannot establish practical
or statistical equivalence. Its cache evicted 24 entries; 29 plans cited at least
one shown entry. The last cache size is bounded, but total archive storage is not.

K=6 was chosen before v2 outcomes using the original records and a hypothetical
32,768-token deployment: reserve 12,000 for output and about 10,000 for fixed input,
then budget about 1,650 tokens per entry. V2 full-history inputs exceed the resulting
20,768-token input allowance at iteration 13; LRU peaks at 16,841 tokens. This is
an **offline deployment-budget comparison**, not an observed provider overflow:
the actual experiment allowed 200,000 input tokens and full history completed.
The observed largest-entry calculation is conditional on these records, not a
guarantee for arbitrarily long future entries. No K sweep or FIFO/random/retrieval
baseline isolates whether LRU recency itself is responsible.

**Conclusion:** bounded history reduced observed input usage while retaining a
similar final latency in this run; neither universal sufficiency nor optimality
of six entries has been demonstrated.

## Limitations and proposal alignment

One replicate per arm, fixed sequential order on one host, a provider alias and
one app/workload prevent significance, equivalence or broad generalization claims.
The strict study was designed after seeing unrestricted results. Thirty dependent
iterations are not 30 independent experimental samples. Repeated timing within
an arm is not a substitute for replicated runs. The 8% acceptance threshold does
not bound uncertainty in cross-arm final gaps.

The correctness suite misses literal substring cases involving `%` and `_`;
SQLite LIKE can treat them as wildcards. Therefore 'passes protected checks'
should not be read as proof of full API equivalence. The LRU self-citation rule
and the extra schema field are additional treatment differences from full history.
A stronger follow-up would add wildcard regression tests, independent seeds and
applications, randomized/counterbalanced arm order, several replicates, a held-out
workload and alternative bounded-memory policies.

The original October study remains separate: 61 of 300 planned final attempts,
one complete pair (2.747 ms stateless vs 0.995 ms full history) and one partial run.
Memory's largest gain occurred on its first attempt, before any history existed.
The planned five pairs were never completed. November's exploratory studies do
not retroactively complete that frozen protocol. The project delivers the proposed
roles, full-history treatment, protected checks and 30-attempt comparisons, with
explicitly labeled LRU, baseline and scope extensions.

## Conclusion

**Takeaway:** A small history cache is a promising way to reduce context cost in
iterative code optimization, but our single-run studies do not establish a
reliable memory advantage. The principal deliverable is an auditable experimental
system and an exploratory comparison that motivates stronger replication.

## Contributions

Jaymeson Koh and Thomas Choo contributed equally across the entire project:
problem formulation, testbed and dataset design, controller and memory policies,
experimentation, analysis, documentation, report writing and presentation.
This equal attribution follows the authors' stated contribution allocation.

## Evidence and deliverables

- Primary overview: `README.md`.
- V2 analysis: `research/testbed-v2/RESULTS.md`; implementation/calibration:
  `research/testbed-v2/README.md`, `calibration.json`, `calibration-strict.json`.
- Exact generated records/workload: `benchmarks/fixtures.py`, `benchmarks/workload.py`.
- Memory and scope: `lru_memory/policy.py`, `lru_memory/engine.py`.
- Raw v2 records: `experiments/soclaas-lru-v2-{unconstrained-2026-11-12,strict-2026-11-13}/`.
- Offline summaries: corresponding `*-report/*/summary.json` files.
- Final report: `output/report/final-project-report.pdf`, with editable LaTeX source
  and the official ACL 2023 style/bibliography files in the same directory.
- The 20-minute presentation is saved in Spaces; speaker notes include timing,
  experiment questions, figure explanations and prompt backups.

All factual results above are from recorded data. This document update is not a
new software-test run or new experiment execution. Older verification counts
are historical and are not presented as checks rerun in November.
'''
old.write_text(text)
print('Updated report',len(text.split()),'words')
