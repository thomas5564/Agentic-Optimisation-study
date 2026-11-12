"""Offline three-arm analysis reusing analysis.report; LRU runs are labelled memory_lru via lru.json."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import html
import json
import math
import os
from pathlib import Path
from statistics import mean
import tempfile

from analysis.report import cohort_key, export_csv, load_runs, stats, summarize
from benchmarks.metrics import write_json
from controller.engine import score
from controller.storage import read_json
from lru_memory.engine import ARMS, is_lru
from lru_memory.policy import replay

COLORS = {"stateless": "#2765b0", "memory": "#c05c21", "memory_lru": "#2e8b57"}
COMPARISONS = (("stateless", "memory"), ("stateless", "memory_lru"), ("memory", "memory_lru"))


def label_runs(runs):
    # Relabel in memory only; archived manifests are never rewritten.
    for run in runs:
        if is_lru(run["root"]):
            run["lru"] = read_json(run["root"] / "lru.json")
            run["manifest"] = {**run["manifest"], "condition": "memory_lru"}
    return runs


def lru_stats(run):
    steps = replay(run["attempts"], run["lru"]["capacity"])
    return {"run_id": run["manifest"]["run_id"], "pair_id": run["manifest"].get("pair_id"), "capacity": run["lru"]["capacity"],
            "attempts": len(steps), "mean_entries_shown": mean(len(s["shown"]) for s in steps) if steps else None,
            "valid_citations": sum(len(s["refreshed"]) for s in steps), "ignored_citations": sum(len(s["ignored"]) for s in steps),
            "evictions": sum(len(s["evicted"]) for s in steps),
            "planner_outputs_with_citations": sum(bool(s["refreshed"] or s["ignored"]) for s in steps)}


def compare(run_rows):
    replicates = defaultdict(dict)
    for row in run_rows:
        if row["pair_id"] is not None:
            replicates[row["pair_id"]][row["condition"]] = row
    out = []
    for rep, members in sorted(replicates.items()):
        entry = {"pair_id": rep}
        for slower, faster in COMPARISONS:
            a, b = members.get(slower), members.get(faster)
            ok = a and b and a["status"] == b["status"] == "complete" and a["final_remeasurement_score_ms"] and b["final_remeasurement_score_ms"]
            entry[f"{slower}_over_{faster}_speedup"] = a["final_remeasurement_score_ms"] / b["final_remeasurement_score_ms"] if ok else None
        out.append(entry)
    return out


def figures(runs, summary, attempts, output, kind):
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "notes-matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
    fig.suptitle(kind, fontsize=11)
    for run in runs:
        m = run["manifest"]
        rows = [r for r in attempts if r["run_id"] == m["run_id"]]
        x = [0] + [r["iteration"] for r in rows]
        y = [1.0 if score(run["baseline"]) else math.nan] + [r["normalized_retained_latency"] if r["normalized_retained_latency"] is not None else math.nan for r in rows]
        ax.step(x, y, where="post", alpha=.4, color=COLORS[m["condition"]], linewidth=1)
    for condition, color in COLORS.items():
        rows = [r for r in summary["trajectories"] if r["condition"] == condition and r["mean"] is not None]
        if rows:
            x, y = [r["iteration"] for r in rows], [r["mean"] for r in rows]
            ax.step(x, y, where="post", label=f"{condition}: mean across runs", color=color, linewidth=2)
            ax.fill_between(x, [r["min"] for r in rows], [r["max"] for r in rows], step="post", color=color, alpha=.1)
    ax.axhline(1, color="gray", linestyle=":")
    ax.set(xlabel="Iteration", ylabel="Retained latency / initial latency", title="Accepted code: last observed latency (lower is better)")
    if ax.get_legend_handles_labels()[0]:
        ax.legend()
    ax.grid(alpha=.2)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    fig.savefig(output / "latency.png", dpi=150)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 4), layout="constrained")
    fig.suptitle(kind, fontsize=11)
    for condition, color in COLORS.items():
        by_iteration = defaultdict(list)
        for row in attempts:
            if row["condition"] == condition and row["correctness"] is not None:
                by_iteration[row["iteration"]].append(float(row["correctness"]))
        if by_iteration:
            x = sorted(by_iteration)
            ax.plot(x, [mean(by_iteration[i]) for i in x], marker="o", label=condition, color=color)
    if ax.get_legend_handles_labels()[0]:
        ax.legend()
    else:
        ax.text(.5, .5, "No measured candidate values", ha="center", transform=ax.transAxes)
    ax.set(xlabel="Iteration", ylabel="Proportion", ylim=(-.05, 1.05), title="Candidate correctness (unavailable checks omitted)")
    ax.grid(alpha=.2)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    fig.savefig(output / "correctness.png", dpi=150)
    plt.close(fig)


def report(runs_dir: Path, output: Path, make_figures=True):
    runs = label_runs(load_runs(runs_dir))
    groups = defaultdict(list)
    for run in runs:
        # LRU capacity is part of the protocol: different K values are separate cohorts.
        run["capacity"] = run.get("lru", {}).get("capacity")
        groups[cohort_key(run["manifest"])].append(run)
    output.mkdir(parents=True, exist_ok=True)
    links = []
    for key, members in sorted(groups.items()):
        capacities = {m["capacity"] for m in members if m["capacity"] is not None}
        if len(capacities) > 1:
            raise ValueError(f"Cohort {key} mixes LRU capacities {sorted(capacities)}; analyse them separately")
        directory = output / key
        directory.mkdir(exist_ok=True)
        summary, attempts, _, _, checkpoints = summarize(members)
        arms = {arm: {metric: stats([r[metric] for r in summary["runs"] if r["condition"] == arm and r["status"] == "complete"])
                      for metric in ("final_remeasurement_score_ms", "baseline_speedup", "accepted_changes",
                                     "correctness_pass_rate", "repeated_unsuccessful_approaches", "input_tokens", "output_tokens")}
                for arm in ARMS}
        comparisons = compare(summary["runs"])
        lru_rows = [lru_stats(m) for m in members if "lru" in m]
        result = {"schema_version": 1, "lru_report_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "analysis": summary, "lru_capacity": next(iter(capacities), None), "arms": arms,
                  "replicate_comparisons": comparisons,
                  "comparison_summary": {k: stats([c[k] for c in comparisons]) for k in comparisons[0] if k != "pair_id"} if comparisons else {},
                  "lru_usage": lru_rows,
                  "note": "Speedup = first arm's final latency / second arm's (>1 means the second arm is faster). Descriptive only; complete runs only."}
        write_json(directory / "summary.json", result)
        common = ["run_id", "pair_id", "condition", "phase", "backend", "synthetic"]
        export_csv(directory / "runs.csv", summary["runs"], list(summary["runs"][0]))
        export_csv(directory / "attempts.csv", attempts, list(attempts[0]) if attempts else common + ["iteration", "status", "accepted"])
        export_csv(directory / "checkpoints.csv", checkpoints, common + ["iteration", "source_hash", "score_ms"])
        export_csv(directory / "comparisons.csv", comparisons, ["pair_id"] + [f"{a}_over_{b}_speedup" for a, b in COMPARISONS])
        if lru_rows:
            export_csv(directory / "lru.csv", lru_rows, list(lru_rows[0]))
        kind = ("SYNTHETIC TEST FIXTURES" if members[0]["manifest"]["synthetic"] else
                "MOCK SMOKE: no conclusion about memory benefits" if members[0]["manifest"]["backend"] == "mock" else
                members[0]["manifest"]["phase"].upper() + " — measured live-agent runs")
        if make_figures:
            figures(members, summary, attempts, directory, kind)
        def cell(value):
            return f"<td>{'' if value['mean'] is None else format(value['mean'], '.4g')} (n={value['n_runs']})</td>"
        rows = "".join(f"<tr><td>{arm}</td>" + "".join(cell(v) for v in arms[arm].values()) + "</tr>" for arm in ARMS)
        table = ("<table border=1 cellpadding=4 style='border-collapse:collapse'><tr><th>arm</th>"
                 + "".join(f"<th>{html.escape(m)}</th>" for m in arms["stateless"]) + "</tr>" + rows + "</table>")
        images = "".join(f'<img src="{n}" alt="{n}" style="max-width:100%">' for n in ("latency.png", "correctness.png")) if make_figures else ""
        (directory / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>Three-arm memory report</title><main style="max-width:1000px;margin:32px auto;font-family:system-ui">'
            f'<h1>{html.escape(key)}</h1><p>{html.escape(kind)}. Independent runs: {len(members)}. LRU capacity: {next(iter(capacities), "n/a")}. Means over complete runs.</p>'
            + table + images + '<p><a href="summary.json">Summary</a> · <a href="comparisons.csv">Replicate comparisons</a> · <a href="lru.csv">LRU usage</a> · <a href="attempts.csv">Attempts</a> · <a href="runs.csv">Runs</a></p></main>')
        links.append(f'<li><a href="{key}/index.html">{html.escape(key)}</a></li>')
    (output / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>Three-arm cohorts</title><h1>Separate experiment cohorts</h1><ul>' + "".join(links) + "</ul>")
    return {"cohorts": sorted(groups), "run_count": len(runs)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args()
    try:
        result = report(args.runs_dir, args.output, make_figures=not args.no_figures)
    except (ValueError, OSError, ImportError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
