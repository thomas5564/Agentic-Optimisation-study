from __future__ import annotations

import json
import math
import os
from pathlib import Path
from statistics import mean, median, stdev
import tempfile


def summarize_samples(samples: list[float]) -> dict:
    if not samples:
        return dict.fromkeys(("mean", "median", "p95", "min", "max"))
    ordered = sorted(samples)
    return {"mean": mean(samples), "median": median(samples),
            "p95": ordered[math.ceil(len(ordered) * .95) - 1],
            "min": min(samples), "max": max(samples)}


def summarize_requests(results: list[dict]) -> dict:
    samples = [r["elapsed_ms"] for r in results if r["elapsed_ms"] is not None]
    successful = sum(r["valid"] for r in results)
    return {"total": len(results), "successful": successful,
            "failed": len(results) - successful,
            "completed": sum(r["status_code"] is not None for r in results),
            "timed_out": sum(r["error"] == "timeout" for r in results),
            "semantic_mismatches": sum(r["error"] == "semantic_mismatch" for r in results),
            "success_rate": successful / len(results) if results else None,
            "latency_ms": summarize_samples(samples)}


def aggregate_runs(runs: list[dict]) -> dict:
    scores = [r["score_ms"] for r in runs]
    valid = bool(scores) and all(s is not None for s in scores)
    measurements = scores if valid else []
    noise = None
    if len(measurements) >= 2:
        center = mean(measurements)
        noise = {"repetition_means_ms": measurements,
                 "coefficient_of_variation": stdev(measurements) / center,
                 "relative_range": (max(measurements) - min(measurements)) / center,
                 "epsilon": None,
                 "note": "Descriptive local noise only. Select and freeze epsilon above observed noise after a representative pilot."}
    requests = [request for run in runs for request in run["requests"]]
    return {"score_ms": median(measurements) if valid else None,
            "valid": valid, "noise": noise, "counts": summarize_requests(requests),
            "per_operation": {op: summarize_requests([r for r in requests if r["operation"] == op])
                              for op in ("add", "get", "update", "delete", "list_search")}}


def write_json(path: str | Path, payload: dict) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".result-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination
