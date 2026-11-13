"""Researcher-only calibration of testbed v2 with the unmodified evaluator (no model calls).

Validates variants against the official suite and measures them with the real benchmark.
`--greedy` repeatedly applies the remaining fix with the largest measured gain, recording
whether each step clears epsilon relative to its parent, as the runner's acceptance rule would.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from benchmarks.metrics import write_json
from controller.config import ExperimentConfig
from controller.engine import decide, score
from controller.evaluation import Evaluator

from build import FIXES, REQUIRES, variant_files


def key(fixes) -> str:
    return "+".join(sorted(fixes)) or "baseline"


class Calibrator:
    def __init__(self, benchmark: dict, epsilon: float, raw: Path, timeout: float):
        self.config = ExperimentConfig(epsilon=epsilon, benchmark=benchmark, evaluation_timeout_seconds=timeout)
        self.evaluator = Evaluator(self.config)
        self.raw = raw
        self.cache: dict[str, dict] = {}

    def measure(self, fixes: set[str]) -> dict:
        name = key(fixes)
        if name not in self.cache:
            started = time.monotonic()
            result = self.evaluator.measure(variant_files(fixes), self.raw / "measure" / name)
            ops = {op: v["latency_ms"]["mean"] for op, v in result.get("aggregate", {}).get("per_operation", {}).items()}
            self.cache[name] = {"fixes": sorted(fixes), "score_ms": score(result), "wall_seconds": round(time.monotonic() - started, 1),
                                "noise": result.get("aggregate", {}).get("noise"), "per_operation_mean_ms": ops, "_raw": result}
            print(f"{name}: {self.cache[name]['score_ms']} ms ({self.cache[name]['wall_seconds']} s)", flush=True)
        return self.cache[name]

    def validate(self, fixes: set[str]) -> dict:
        result = self.evaluator.validate(variant_files(fixes), self.raw / "validate" / key(fixes))
        print(f"validate {key(fixes)}: {result['status']}", flush=True)
        return {"fixes": sorted(fixes), "correct": result.get("correct"), "status": result.get("status")}


def available(applied: set[str]) -> list[str]:
    return [f for f in FIXES if f not in applied and REQUIRES.get(f, f) in applied | {f}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Experiment config whose benchmark/epsilon to use")
    parser.add_argument("--repetitions", type=int, help="Override benchmark repetitions for faster probes")
    parser.add_argument("--raw", type=Path, required=True, help="Directory for raw evaluator artifacts")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validate", action="store_true", help="Run the official suite on baseline, reference and each single fix")
    parser.add_argument("--greedy", action="store_true", help="Measure single-fix ablations and a greedy acceptance path")
    parser.add_argument("--only", help="Comma-separated fixes the greedy path may use (e.g. those that comply with --strict-scope)")
    args = parser.parse_args()
    import yaml
    settings = yaml.safe_load(args.config.read_text())
    benchmark = {**settings["benchmark"], **({"repetitions": args.repetitions} if args.repetitions else {})}
    calibrator = Calibrator(benchmark, settings["epsilon"], args.raw, settings.get("evaluation_timeout_seconds", 300))
    report = {"schema_version": 1, "config": str(args.config), "benchmark": benchmark, "epsilon": settings["epsilon"],
              "fixes": {name: {"approach": a, "description": d} for name, (a, d) in FIXES.items()}, "requires": REQUIRES}
    if args.validate:
        report["validation"] = [calibrator.validate(f) for f in [set(), set(FIXES)] + [{f, *([REQUIRES[f]] if f in REQUIRES else [])} for f in FIXES]]
    baseline = calibrator.measure(set())
    reference = calibrator.measure(set(FIXES))
    report["baseline"] = {k: v for k, v in baseline.items() if k != "_raw"}
    report["reference"] = {k: v for k, v in reference.items() if k != "_raw"}
    if args.greedy:
        singles = {}
        for fix in FIXES:
            if args.only and fix not in args.only.split(","):
                continue
            fixes = {fix, *([REQUIRES[fix]] if fix in REQUIRES else [])}
            m = calibrator.measure(fixes)
            singles[fix] = {"fixes": sorted(fixes), "score_ms": m["score_ms"],
                            "improvement_vs_baseline": decide({"correct": True}, baseline["_raw"], m["_raw"], settings["epsilon"], "evaluated").relative_improvement}
        report["single_fix_ablation"] = singles
        applied: set[str] = set()
        parent = baseline
        path = []
        allowed = set(args.only.split(",")) if args.only else set(FIXES)
        while [f for f in available(applied) if f in allowed]:
            trials = {f: calibrator.measure(applied | {f}) for f in available(applied) if f in allowed}
            best = min(trials, key=lambda f: trials[f]["score_ms"] if trials[f]["score_ms"] else float("inf"))
            decision = decide({"correct": True}, parent["_raw"], trials[best]["_raw"], settings["epsilon"], "evaluated")
            path.append({"step": len(path) + 1, "fix": best, "parent_ms": parent["score_ms"], "candidate_ms": trials[best]["score_ms"],
                         "relative_improvement": decision.relative_improvement, "accepted_at_epsilon": decision.accepted,
                         "alternatives": {f: t["score_ms"] for f, t in trials.items()}})
            applied.add(best)
            parent = trials[best]
        report["greedy_path"] = path
        report["accepted_steps"] = sum(step["accepted_at_epsilon"] for step in path)
    report["total_speedup"] = baseline["score_ms"] / reference["score_ms"] if baseline["score_ms"] and reference["score_ms"] else None
    write_json(args.output, report)
    print(json.dumps({k: report[k] for k in ("total_speedup",) + (("accepted_steps",) if args.greedy else ())}))


if __name__ == "__main__":
    main()
