"""Offline, replicate-level descriptive analysis; missing values remain missing."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import html
import hashlib
import json
import math
import os
from pathlib import Path
from statistics import mean, stdev
import tempfile

from benchmarks.metrics import write_json
from benchmarks.run import content_hash
from controller.engine import score
from controller.storage import read_json


def optional_sum(values):
    return sum(values) if values and all(v is not None for v in values) else None


def stats(values):
    values = [v for v in values if v is not None and math.isfinite(v)]
    return {"n_runs": len(values), "mean": mean(values) if values else None,
            "sample_sd": stdev(values) if len(values) > 1 else None,
            "min": min(values) if values else None, "max": max(values) if values else None}


def journal_result(root, key):
    path = root / "journal" / f"{key}.json"
    if not path.exists():
        return None
    saved = read_json(path)
    return saved.get("result") if saved.get("status") == "complete" else None


def load_runs(directory: Path):
    paths = [directory / "manifest.json"] if (directory / "manifest.json").exists() else sorted(directory.rglob("manifest.json"))
    runs = []
    for path in paths:
        manifest = read_json(path)
        if "run_id" not in manifest or "condition" not in manifest:
            continue
        root = path.parent
        attempts = [read_json(p) for p in sorted((root / "attempts").glob("*.json"))]
        if any(a["iteration"] != i or a["run_id"] != manifest["run_id"] for i, a in enumerate(attempts, 1)):
            raise ValueError(f"Invalid attempt sequence in {root}")
        runs.append({"root": root, "manifest": manifest, "attempts": attempts,
                     "baseline": journal_result(root, "baseline-measure"),
                     "final": journal_result(root, "final-remeasurement"),
                     "state": read_json(root / "state.json") if (root / "state.json").exists() else {"status": "incomplete"}})
    if not runs:
        raise ValueError("No archived controller runs found")
    if len({r["manifest"]["run_id"] for r in runs}) != len(runs):
        raise ValueError("Duplicate run IDs; do not treat copies as independent replicates")
    return runs


def cohort_key(manifest):
    comparable = {"protocol": manifest["protocol_hash"], "implementation": manifest["implementation"], "environment": manifest["environment"]}
    return f"{manifest['phase']}-{manifest['backend']}-{'synthetic' if manifest['synthetic'] else 'measured'}-{content_hash(comparable)[:12]}"


def export_csv(path, rows, fields):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def summarize(runs):
    attempts_out, requests_out, repetitions_out, run_rows, checkpoints, operations = [], [], [], [], [], []
    curves = defaultdict(list)
    for run in runs:
        manifest, attempts = run["manifest"], run["attempts"]
        identity = {"run_id": manifest["run_id"], "pair_id": manifest.get("pair_id"),
                    "condition": manifest["condition"], "phase": manifest["phase"],
                    "backend": manifest["backend"], "synthetic": manifest["synthetic"]}
        baseline = score(run["baseline"])
        if baseline:
            curves[(manifest["condition"], 0)].append(1.0)
        rejected_keys = set()
        repeated = 0
        usages = []
        correctness = []
        def measurement_rows(measurement, iteration, side):
            if not measurement:
                return
            for operation, values in measurement.get("aggregate", {}).get("per_operation", {}).items():
                operations.append({**identity, "iteration": iteration, "side": side, "operation": operation,
                                   "mean_ms": values.get("latency_ms", {}).get("mean"), "p95_ms": values.get("latency_ms", {}).get("p95"),
                                   "successful": values.get("successful"), "failed": values.get("failed"), "timed_out": values.get("timed_out")})
            for rep_index, rep in enumerate(measurement.get("runs", [])):
                counts = rep.get("counts", {})
                repetitions_out.append({**identity, "iteration": iteration, "side": side, "repetition": rep_index,
                                        "score_ms": rep.get("score_ms"), "total": counts.get("total"),
                                        "successful": counts.get("successful"), "failed": counts.get("failed"),
                                        "timed_out": counts.get("timed_out")})
                for request_index, request in enumerate(rep.get("requests", [])):
                    requests_out.append({**identity, "iteration": iteration, "side": side, "repetition": rep_index,
                                         "request_index": request_index, **request})
        measurement_rows(run["baseline"], 0, "baseline")
        for attempt in attempts:
            plan = attempt.get("plan") or {}
            key = (plan.get("approach"), " ".join(plan.get("change", "").casefold().split()))
            is_repeated = bool(key[1]) and key in rejected_keys
            repeated += is_repeated
            if not attempt["decision"]["accepted"] and key[1]:
                rejected_keys.add(key)
            validation = attempt.get("validation") or {}
            correct = validation.get("correct") if validation.get("status") in {"passed", "syntax_failed", "startup_failed", "correctness_failed", "validation_timeout"} else None
            if correct is not None:
                correctness.append(correct)
            candidate = attempt.get("candidate_measurement")
            counts = (candidate or {}).get("aggregate", {}).get("counts", {})
            retained = attempt.get("retained_score_ms")
            normalized = retained / baseline if retained is not None and baseline else None
            curves[(manifest["condition"], attempt["iteration"])].append(normalized)
            usages.extend(role.get("usage") for role in attempt.get("roles", {}).values())
            attempts_out.append({**identity, "iteration": attempt["iteration"], "status": attempt["status"],
                "accepted": attempt["decision"]["accepted"], "correctness": correct,
                "parent_hash": attempt["parent_hash"], "candidate_hash": attempt["candidate_hash"], "retained_hash": attempt["retained_hash"],
                "parent_score_ms": score(attempt.get("parent_measurement")), "candidate_score_ms": score(candidate),
                "retained_score_ms": retained, "normalized_retained_latency": normalized,
                "retained_score_carried_forward": not attempt.get("parent_measurement") and not attempt["decision"]["accepted"],
                "candidate_request_success_rate": counts.get("success_rate"), "successful_requests": counts.get("successful"),
                "failed_requests": counts.get("failed"), "repeated_unsuccessful_approach": is_repeated,
                "approach": plan.get("approach"), "audit_status": attempt["audit_status"]})
            measurement_rows(attempt.get("parent_measurement"), attempt["iteration"], "parent")
            measurement_rows(candidate, attempt["iteration"], "candidate")
        measurement_rows(run["final"], len(attempts), "final_remeasurement")
        for path in sorted((run["root"] / "checkpoints").glob("*.json")):
            checkpoint = read_json(path)
            checkpoints.append({**identity, "iteration": checkpoint["iteration"], "source_hash": checkpoint["source_hash"],
                                "score_ms": score(checkpoint["measurement"])})
            measurement_rows(checkpoint["measurement"], checkpoint["iteration"], "checkpoint")
        run_rows.append({**identity, "status": run["state"]["status"], "planned_iterations": manifest["iterations"],
            "completed_iterations": len(attempts), "accepted_changes": sum(a["decision"]["accepted"] for a in attempts),
            "evaluated_candidates": len(correctness), "correctness_pass_rate": mean(correctness) if correctness else None,
            "repeated_unsuccessful_approaches": repeated, "baseline_score_ms": baseline,
            "final_remeasurement_score_ms": score(run["final"]),
            "baseline_speedup": baseline / score(run["final"]) if baseline and score(run["final"]) else None,
            "input_tokens": optional_sum([(u or {}).get("input_tokens") for u in usages]),
            "output_tokens": optional_sum([(u or {}).get("output_tokens") for u in usages]),
            "cost_usd": optional_sum([(u or {}).get("cost_usd") for u in usages])})
    trajectories = [{"condition": condition, "iteration": iteration, **stats(values)} for (condition, iteration), values in sorted(curves.items())]
    comparisons = []
    paired = defaultdict(dict)
    for run, row in zip(runs, run_rows):
        pair = row["pair_id"]
        if pair is not None:
            if row["condition"] in paired[pair]:
                raise ValueError("Duplicate condition within replicate pair")
            paired[pair][row["condition"]] = (run, row)
    for pair, members in sorted(paired.items()):
        stateless, memory = members.get("stateless"), members.get("memory")
        ratio = None
        if stateless and memory:
            if stateless[0]["manifest"]["config"]["benchmark"] != memory[0]["manifest"]["config"]["benchmark"]:
                raise ValueError("Paired conditions have different workloads/seeds")
            before, after = stateless[1]["final_remeasurement_score_ms"], memory[1]["final_remeasurement_score_ms"]
            if before and after and stateless[1]["status"] == memory[1]["status"] == "complete":
                ratio = before / after
        comparisons.append({"pair_id": pair, "stateless_over_memory_speedup": ratio})
    summary = {"schema_version": 1, "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "operations": operations, "runs": run_rows, "trajectories": trajectories, "paired_final_comparisons": comparisons,
               "paired_speedup_summary": stats([p["stateless_over_memory_speedup"] for p in comparisons]),
               "uncertainty": "Sample SD/range across independent runs, never across iterations. Descriptive only; no significance claim.",
               "repetition_rubric": "Repeated unsuccessful approach = same approach category and exact case-folded, whitespace-normalized proposed change after an earlier rejection. No semantic inference.",
               "retained_curve": "Last observed accepted-code latency; carried values are explicit, not independent remeasurements. Incomplete runs are not extrapolated.",
               "missing": "Missing metrics/tokens/cost are null (blank CSV cells), not zero."}
    return summary, attempts_out, requests_out, repetitions_out, checkpoints


def figures(runs, summary, attempts, output):
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "notes-matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    colors = {"stateless": "#2765b0", "memory": "#c05c21"}
    kind = ("SYNTHETIC TEST FIXTURES" if runs[0]["manifest"]["synthetic"] else
            "MOCK SMOKE: no conclusion about memory benefits" if runs[0]["manifest"]["backend"] == "mock" else
            runs[0]["manifest"]["phase"].upper() + " — measured live-agent runs")
    fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
    fig.suptitle(kind, fontsize=11)
    for run in runs:
        m = run["manifest"]
        rows = [r for r in attempts if r["run_id"] == m["run_id"]]
        x = [0] + [r["iteration"] for r in rows]
        y = [1.0 if score(run["baseline"]) else math.nan] + [r["normalized_retained_latency"] if r["normalized_retained_latency"] is not None else math.nan for r in rows]
        ax.step(x, y, where="post", alpha=.4, color=colors[m["condition"]], linewidth=1)
    for condition, color in colors.items():
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
    for metric, filename, title in (("correctness", "correctness.png", "Candidate correctness (unavailable checks omitted)"),
                                     ("candidate_request_success_rate", "request-success.png", "Timed candidate request success (missing measurements omitted)")):
        fig, ax = plt.subplots(figsize=(9, 4), layout="constrained")
        fig.suptitle(kind, fontsize=11)
        for condition, color in colors.items():
            by_iteration = defaultdict(list)
            for row in attempts:
                if row["condition"] == condition and row[metric] is not None:
                    by_iteration[row["iteration"]].append(float(row[metric]))
            if by_iteration:
                x = sorted(by_iteration)
                ax.plot(x, [mean(by_iteration[i]) for i in x], marker="o", label=condition, color=color)
        if ax.get_legend_handles_labels()[0]:
            ax.legend()
        else:
            ax.text(.5, .5, "No measured candidate values", ha="center", transform=ax.transAxes)
        ax.set(xlabel="Iteration", ylabel="Proportion", ylim=(-.05, 1.05), title=title)
        ax.grid(alpha=.2)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        fig.savefig(output / filename, dpi=150)
        plt.close(fig)


def report(runs_dir: Path, output: Path, make_figures=True):
    runs = load_runs(runs_dir)
    groups = defaultdict(list)
    for run in runs:
        groups[cohort_key(run["manifest"])].append(run)
    output.mkdir(parents=True, exist_ok=True)
    (output / "analysis_source.py").write_text(Path(__file__).read_text())
    links = []
    for key, members in sorted(groups.items()):
        directory = output / key
        directory.mkdir(exist_ok=True)
        summary, attempts, requests, repetitions, checkpoints = summarize(members)
        write_json(directory / "summary.json", summary)
        common = ["run_id", "pair_id", "condition", "phase", "backend", "synthetic"]
        export_csv(directory / "operations.csv", summary["operations"], common + ["iteration", "side", "operation", "mean_ms", "p95_ms", "successful", "failed", "timed_out"])
        export_csv(directory / "runs.csv", summary["runs"], list(summary["runs"][0]))
        export_csv(directory / "attempts.csv", attempts, list(attempts[0]) if attempts else common + ["iteration", "status", "accepted"])
        export_csv(directory / "requests.csv", requests, common + ["iteration", "side", "repetition", "request_index", "name", "operation", "status_code", "elapsed_ms", "valid", "error"])
        export_csv(directory / "repetitions.csv", repetitions, common + ["iteration", "side", "repetition", "score_ms", "total", "successful", "failed", "timed_out"])
        export_csv(directory / "checkpoints.csv", checkpoints, common + ["iteration", "source_hash", "score_ms"])
        if make_figures:
            figures(members, summary, attempts, directory)
        images = ''.join(f'<img src="{name}" alt="{html.escape(name)}" style="max-width:100%">' for name in ["latency.png", "correctness.png", "request-success.png"]) if make_figures else ""
        (directory / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>Optimization experiment report</title><main style="max-width:1000px;margin:32px auto;font-family:system-ui">'
            f'<h1>{html.escape(key)}</h1><p>Independent runs: {len(members)}. Mock and synthetic results are development evidence only.</p>'
            '<p>Thin lines show individual runs; the band is the observed range across runs. Retained latency uses the latest measurement of accepted code; carried values are not new observations. Missing values are omitted.</p>'
            + images + '<p><a href="summary.json">Machine-readable summary</a> · <a href="attempts.csv">Attempts</a> · <a href="requests.csv">Requests</a> · <a href="repetitions.csv">Repetitions</a> · <a href="runs.csv">Runs and usage</a></p></main>')
        links.append(f'<li><a href="{key}/index.html">{html.escape(key)}</a></li>')
    (output / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>Experiment cohorts</title><h1>Separate experiment cohorts</h1><p>Different protocols, phases, backends, and synthetic/measured data are never pooled.</p><ul>' + ''.join(links) + '</ul>')
    return {"cohorts": list(sorted(groups)), "run_count": len(runs)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = report(args.runs_dir, args.output)
    except (ValueError, OSError, ImportError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
