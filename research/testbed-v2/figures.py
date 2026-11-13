"""Researcher-only figures for the testbed v2 three-arm runs (no model calls).

Reads recorded attempt records and draws, for each study and arm: speedup and latency per
iteration, input tokens, attempt outcomes, iterations to convergence, and (for the LRU capacity)
Planner prompt size against the 32k context budget. Single replicates: descriptive only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import NullFormatter
import numpy as np

CONTEXT_TOKENS, OUTPUT_RESERVE = 32_768, 12_000  # 32k deployment and the configured output reserve
CONVERGED = 1.05  # converged once retained latency stays within 5% of the arm's final value
OUTCOMES = (("accepted", "accepted", "#2e8b57"), ("too small", "passed tests, gain below epsilon", "#9cc3a6"),
            ("noop", "no change", "#c8c8c8"), ("tests failed", "failed official tests / syntax", "#d0473a"),
            ("malformed", "malformed output or timeout", "#7a4fa0"), ("scope", "scope_exceeded", "#e8a33c"))
ARMS = (("memory_lru", "memory + LRU (K=6)", "#2e8b57"), ("memory", "full memory", "#c05c21"), ("stateless", "stateless", "#2765b0"))


def load(run: Path) -> dict:
    attempts = [json.loads(p.read_text()) for p in sorted((run / "attempts").glob("*.json"))]
    baseline = next(a["parent_measurement"]["aggregate"]["score_ms"] for a in attempts if a.get("parent_measurement"))
    tokens = sum((r.get("usage") or {}).get("input_tokens", 0) or (r.get("usage") or {}).get("prompt_tokens", 0)
                 for a in attempts for r in (a.get("roles") or {}).values())
    latency = [baseline] + [a["retained_score_ms"] for a in attempts]
    accepted = [a["iteration"] for a in attempts if (a.get("decision") or {}).get("accepted")]
    final = latency[-1]
    converged = next(i for i in range(len(latency)) if all(v <= final * CONVERGED for v in latency[i:]))
    planner = [((a.get("roles") or {}).get("planner") or {}).get("usage") or {} for a in attempts]
    shown = [len(read(run / "lru" / f"{a['iteration']:03d}.json")["shown"]) if (run / "lru.json").exists()
             else (a["iteration"] - 1 if a["condition"] == "memory" else 0) for a in attempts]
    return {"latency": latency, "baseline": baseline, "accepted": accepted, "input_tokens": tokens,
            "converged_iteration": converged, "outcomes": [outcome(a) for a in attempts],
            "planner_tokens": [u.get("input_tokens") or u.get("prompt_tokens") for u in planner], "entries_shown": shown,
            "entry_chars": [len(json.dumps(a["memory"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)) for a in attempts]}


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def outcome(attempt: dict) -> str:
    status = attempt["status"]
    if (attempt.get("decision") or {}).get("accepted"):
        return "accepted"
    if status == "evaluated":
        return "too small"
    if status == "noop":
        return "noop"
    if status == "scope_exceeded":
        return "scope"
    if status in ("correctness_failed", "syntax_failed", "patch_rejected"):
        return "tests failed"
    return "malformed"


def arm_dir(study: Path, arm: str) -> Path:
    # Separate-arm runs use the arm name; batch runs use rep-00-<arm>.
    return study / arm if (study / arm).exists() else study / f"rep-00-{arm}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", nargs=2, action="append", metavar=("TITLE", "DIR"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data = {title: {arm: load(arm_dir(Path(d), arm)) for arm, _, _ in ARMS} for title, d in args.study}

    # Speedup over baseline on a log2 axis: each gridline is a doubling, and equal steps look equal.
    fig, axes = plt.subplots(1, len(data), figsize=(6.4 * len(data), 4.8), sharey=True, constrained_layout=True)
    axes = list(axes) if len(data) > 1 else [axes]
    for ax, (title, arms) in zip(axes, data.items()):
        for arm, label, color in ARMS:
            run = arms[arm]
            speedup = [run["baseline"] / v for v in run["latency"]]
            ax.step(range(len(speedup)), speedup, where="post", color=color, lw=2.2,
                    label=f"{label}: {speedup[-1]:.1f}× final, {len(run['accepted'])} accepted")
            ax.plot(run["accepted"], [speedup[i] for i in run["accepted"]], "o", color=color, ms=5)
        ax.set_yscale("log", base=2)
        ax.set_yticks([1, 2, 4, 8], ["1×", "2×", "4×", "8×"])
        ax.set(title=title, xlabel="Iteration", xlim=(0, 30), ylim=(.9, 12))
        ax.grid(alpha=.3)
    axes[0].set_ylabel("Speedup over baseline (log scale, higher is better)")
    for ax in axes:
        ax.legend(fontsize=8.5, loc="lower right")
    fig.suptitle("Testbed v2: speedup of retained code per iteration (dots = accepted steps; one replicate each)")
    fig.savefig(args.output / "latency-comparison.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 3.8), constrained_layout=True)
    width = .8 / len(data)
    for i, (title, arms) in enumerate(data.items()):
        values = [arms[arm]["input_tokens"] / 1e6 for arm, _, _ in ARMS]
        bars = ax.bar([x + i * width for x in range(len(ARMS))], values, width, label=title,
                      color=[c for _, _, c in ARMS], alpha=1 - .45 * i, edgecolor="black", lw=.5)
        ax.bar_label(bars, fmt="%.2fM", fontsize=8)
    ax.set_xticks([x + width * (len(data) - 1) / 2 for x in range(len(ARMS))], [l for _, l, _ in ARMS])
    ax.set(ylabel="Input tokens (millions)", title="Input tokens per arm over 30 iterations")
    # Bars are coloured by arm; studies differ by shade, so the legend shows shade only.
    handles = [plt.Rectangle((0, 0), 1, 1, color="dimgray", alpha=1 - .45 * i) for i in range(len(data))]
    ax.legend(handles, list(data), fontsize=8, loc="upper center", bbox_to_anchor=(.5, -.12), ncol=len(data), frameon=False)
    ax.set_ylim(0, max(arms[arm]["input_tokens"] for arms in data.values() for arm, _, _ in ARMS) / 1e6 * 1.12)
    fig.savefig(args.output / "tokens.png", dpi=150)
    plt.close(fig)

    # Latency in milliseconds on a log axis.
    fig, axes = plt.subplots(1, len(data), figsize=(6.4 * len(data), 4.8), sharey=True, constrained_layout=True)
    axes = list(axes) if len(data) > 1 else [axes]
    for ax, (title, arms) in zip(axes, data.items()):
        for arm, label, color in ARMS:
            run = arms[arm]
            ax.step(range(len(run["latency"])), run["latency"], where="post", color=color, lw=2.2,
                    label=f"{label}: {run['latency'][-1]:.3f} ms final")
            ax.plot(run["accepted"], [run["latency"][i] for i in run["accepted"]], "o", color=color, ms=5)
        ax.set_yscale("log")
        ax.set_yticks([0.5, 1, 2, 4], ["0.5", "1", "2", "4"])
        ax.yaxis.set_minor_formatter(NullFormatter())
        ax.set(title=title, xlabel="Iteration", xlim=(0, 30), ylim=(.4, 6))
        ax.grid(alpha=.3, which="both")
        ax.legend(fontsize=8.5, loc="upper right")
    axes[0].set_ylabel("Retained latency, ms (log scale, lower is better)")
    fig.suptitle("Testbed v2: latency of retained code per iteration (dots = accepted steps; one replicate each)")
    fig.savefig(args.output / "latency-log.png", dpi=150)
    plt.close(fig)

    # Outcome of every attempt, per arm and study.
    rows = [(f"{label}\n{title.split(' (')[0]}", arms[arm]["outcomes"]) for title, arms in data.items() for arm, label, _ in ARMS]
    fig, ax = plt.subplots(figsize=(9, .55 * len(rows) + 1.6), constrained_layout=True)
    for y, (_, outcomes) in enumerate(rows):
        left = 0
        for key, _, color in OUTCOMES:
            n = outcomes.count(key)
            if n:
                ax.barh(y, n, left=left, color=color, edgecolor="white")
                ax.text(left + n / 2, y, str(n), ha="center", va="center", fontsize=8)
                left += n
        errors = sum(outcomes.count(k) for k in ("tests failed", "malformed"))
        ax.text(31, y, f"{errors / len(outcomes):.0%} errors", va="center", fontsize=8.5)
    ax.set_yticks(range(len(rows)), [r for r, _ in rows], fontsize=8.5)
    ax.invert_yaxis()
    ax.set(xlim=(0, 36), xlabel="Attempts (30 per arm)", title="Attempt outcomes (errors = failed tests/syntax + malformed output)")
    ax.legend([plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in OUTCOMES], [l for _, l, _ in OUTCOMES],
              fontsize=8, loc="upper center", bbox_to_anchor=(.5, -.14), ncol=3, frameon=False)
    fig.savefig(args.output / "outcomes.png", dpi=150)
    plt.close(fig)

    # Iterations until retained latency stays within 5% of its final value.
    fig, ax = plt.subplots(figsize=(7, 3.8), constrained_layout=True)
    width = .8 / len(data)
    for i, (title, arms) in enumerate(data.items()):
        values = [arms[arm]["converged_iteration"] for arm, _, _ in ARMS]
        bars = ax.bar([x + i * width for x in range(len(ARMS))], values, width, color=[c for _, _, c in ARMS],
                      alpha=1 - .45 * i, edgecolor="black", lw=.5)
        ax.bar_label(bars, fontsize=8)
    ax.set_xticks([x + width * (len(data) - 1) / 2 for x in range(len(ARMS))], [l for _, l, _ in ARMS])
    ax.set(ylabel="Iteration", ylim=(0, 32), title="Iterations to convergence (latency stays within 5% of final)")
    handles = [plt.Rectangle((0, 0), 1, 1, color="dimgray", alpha=1 - .45 * i) for i in range(len(data))]
    ax.legend(handles, list(data), fontsize=8, loc="upper center", bbox_to_anchor=(.5, -.12), ncol=len(data), frameon=False)
    fig.savefig(args.output / "convergence.png", dpi=150)
    plt.close(fig)

    # LRU capacity: Planner prompt size grows with memory entries; K is what fits the 32k budget.
    fits = {}
    for title, arms in data.items():
        run = arms["memory"]
        pairs = [(n, t) for n, t in zip(run["entries_shown"], run["planner_tokens"]) if t]
        slope, intercept = np.polyfit([n for n, _ in pairs], [t for _, t in pairs], 1)
        # Convert the largest entry's size to tokens with this run's own chars-per-token ratio.
        largest = max(run["entry_chars"]) * slope / np.mean(run["entry_chars"])
        room = CONTEXT_TOKENS - OUTPUT_RESERVE - intercept
        fits[title] = {"tokens_per_entry": slope, "fixed_tokens": intercept, "largest_entry_tokens": largest,
                       "average_capacity": int(room // slope), "worst_case_capacity": int(room // largest),
                       "full_memory_over_budget_from": next((i + 1 for i, t in enumerate(run["planner_tokens"]) if t and t > CONTEXT_TOKENS - OUTPUT_RESERVE), None),
                       "lru_peak_prompt_tokens": max(t for t in arms["memory_lru"]["planner_tokens"] if t)}
    title, arms = list(data.items())[-1]
    fit = fits[title]
    budget = CONTEXT_TOKENS - OUTPUT_RESERVE
    fig, ax = plt.subplots(figsize=(8, 4.4), constrained_layout=True)
    for arm, label, color in ARMS:
        run = arms[arm]
        ax.plot(range(1, len(run["planner_tokens"]) + 1), run["planner_tokens"], "o-", ms=3, color=color, label=label)
    ax.axhline(budget, color="black", ls="--", lw=1)
    ax.text(1, budget * 1.02, f"input budget on a 32k deployment: {CONTEXT_TOKENS:,} − {OUTPUT_RESERVE:,} output reserve = {budget:,}",
            fontsize=8)
    ax.set(xlabel="Iteration", ylabel="Planner prompt tokens", xlim=(0, 31),
           title=f"Planner prompt size vs the 32k input budget ({title.split(' (')[0]} study)")
    ax.text(.985, .04, f"fixed prompt ≈ {fit['fixed_tokens']:,.0f} tokens; each memory entry ≈ {fit['tokens_per_entry']:,.0f} on average,\n"
            f"largest ≈ {fit['largest_entry_tokens']:,.0f}. Entries that fit: {fit['average_capacity']} on average, "
            f"{fit['worst_case_capacity']} in the worst case.\n"
            f"K = 6 (set before the runs from the original records' largest entry, 1,650 tokens).\n"
            f"Full memory exceeds the budget from iteration {fit['full_memory_over_budget_from']}; "
            f"LRU peaks at {fit['lru_peak_prompt_tokens']:,} tokens.",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8,
            bbox={"boxstyle": "round", "facecolor": "white", "edgecolor": "lightgray"})
    ax.grid(alpha=.3)
    ax.legend(fontsize=8.5, loc="upper left", bbox_to_anchor=(0, .9))
    fig.savefig(args.output / "lru-capacity.png", dpi=150)
    plt.close(fig)

    summary = {title: {arm: {k: v for k, v in run.items() if k not in ("latency", "entry_chars")} | {"final_retained_ms": run["latency"][-1]}
                       for arm, run in arms.items()} for title, arms in data.items()}
    summary["lru_capacity_fit"] = fits
    (args.output / "figures.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
