from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sqlite3
import time
from datetime import datetime, timezone

import httpx

from benchmarks.config import BenchmarkConfig, load_config
from benchmarks.fixtures import make_fixture
from benchmarks.metrics import aggregate_runs, summarize_requests, write_json
from benchmarks.reset import reset_database
from benchmarks.runtime import PROJECT_ROOT, benchmark_lock, candidate_server
from benchmarks.workload import build_warmup, build_workload


def content_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def source_manifest(root: Path) -> dict:
    files = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted((root / "app").rglob("*"))
             if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    return {"sha256": content_hash(files), "files": files}


def execute_trace(client, oracle, trace: list[dict]) -> dict:
    results = []
    trace_start = time.perf_counter()
    for step in trace:
        result = {"name": step["name"], "operation": step["operation"],
                  "status_code": None, "elapsed_ms": None, "valid": False,
                  "error": None}
        try:
            path = oracle.path(step)
        except KeyError:
            result["error"] = "failed_dependency"
            results.append(result)
            continue
        start = time.perf_counter()
        try:
            kwargs = {"params": step.get("params", {})}
            if "payload" in step:
                kwargs["json"] = step["payload"]
            response = client.request(step["method"], path, **kwargs)
            result["elapsed_ms"] = (time.perf_counter() - start) * 1000
            result["status_code"] = response.status_code
            try:
                payload = response.json() if response.content else None
                result["valid"] = oracle.check(step, response.status_code, payload, response.content)
            except (ValueError, TypeError, KeyError):
                result["valid"] = False
            if not result["valid"]:
                result["error"] = "semantic_mismatch"
        except httpx.TimeoutException:
            result["error"] = "timeout"
        except httpx.TransportError:
            result["error"] = "transport_error"
        if result["elapsed_ms"] is None:
            result["elapsed_ms"] = (time.perf_counter() - start) * 1000
        results.append(result)
    elapsed_ms = (time.perf_counter() - trace_start) * 1000
    summary = summarize_requests(results)
    return {"requests": results, "counts": summary, "workload_elapsed_ms": elapsed_ms,
            "per_operation": {op: summarize_requests([r for r in results if r["operation"] == op])
                              for op in ("add", "get", "update", "delete", "list_search")},
            "score_ms": summary["latency_ms"]["mean"] if results and not summary["failed"] else None}


def run_once(config: BenchmarkConfig, app_root: Path, log_path: Path, profile: Path | None = None) -> dict:
    stage = "startup"
    result = {"startup_status": "pending", "fixture_status": "pending", "warmups": [],
              "requests": [], "score_ms": None, "error": None,
              "official_tests": None}
    try:
        with candidate_server(app_root, config, log_path, profile) as (client, active):
            result["startup_status"] = "passed"
            stage = "fixture"
            oracle = reset_database(client, seed=config.seed, count=config.note_count)
            result["fixture_status"] = "passed"
            result["logical_fixture_hash"] = content_hash(list(oracle.notes.values()))
            stage = "warmup"
            for _ in range(config.warmups):
                warmup = execute_trace(client, oracle, build_warmup())
                result["warmups"].append(warmup)
                if warmup["score_ms"] is None:
                    raise ValueError("Warm-up response validation failed")
            stage = "workload"
            if profile:
                active.touch()
            try:
                result.update(execute_trace(client, oracle, build_workload(config.seed, config.note_count, config.cycles)))
            finally:
                if profile:
                    active.unlink(missing_ok=True)
            if profile:
                result["score_ms"] = None
    except (RuntimeError, TimeoutError, ValueError, httpx.TransportError) as error:
        result["error"] = {"stage": stage, "type": type(error).__name__, "message": str(error)}
        result[f"{stage}_status"] = "failed"
        result["score_ms"] = None
    return result


def environment() -> dict:
    return {"python": platform.python_version(), "platform": platform.platform(),
            "machine": platform.machine(), "sqlite": sqlite3.sqlite_version,
            "dependencies": {name: importlib.metadata.version(name) for name in
                             ("fastapi", "pydantic", "starlette", "uvicorn", "httpx", "pytest", "PyYAML")}}


def run_benchmark(config: BenchmarkConfig, output: Path, app_root: Path = PROJECT_ROOT) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    if (output / "benchmark_summary.json").exists():
        raise ValueError("Benchmark output already exists; use a fresh output directory")
    manifest = source_manifest(app_root)
    trace = build_workload(config.seed, config.note_count, config.cycles)
    payload = {"schema_version": 1, "kind": "baseline_measurement", "synthetic": False,
               "created_at": datetime.now(timezone.utc).isoformat(),
               "config": config.to_dict(), "config_hash": content_hash(config.to_dict()),
               "source": manifest, "environment": environment(),
               "harness_files": {p.relative_to(PROJECT_ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted((PROJECT_ROOT / "benchmarks").glob("*.py"))},
               "dependency_lock_sha256": hashlib.sha256((PROJECT_ROOT / "requirements.lock").read_bytes()).hexdigest(),
               "trace": trace, "trace_hash": content_hash(trace),
               "fixture_hash": content_hash(make_fixture(config.seed, config.note_count)),
               "warmup_trace": build_warmup(), "runs": []}
    with benchmark_lock():
        for index in range(config.repetitions):
            run = run_once(config, app_root, output / f"server-{index}.log")
            payload["runs"].append({"run_index": index, **run})
            payload["aggregate"] = aggregate_runs(payload["runs"])
            # Preserve completed repetitions even if interrupted later.
            payload["complete"] = index + 1 == config.repetitions
            write_json(output / "benchmark_summary.json", payload)
    if source_manifest(app_root) != manifest:
        payload["aggregate"]["valid"] = False
        payload["aggregate"]["score_ms"] = None
        payload["error"] = "Application source changed during measurement"
        write_json(output / "benchmark_summary.json", payload)
    return payload


def main():
    parser = argparse.ArgumentParser(description="Measure the notes API over real loopback HTTP")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--app-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    try:
        payload = run_benchmark(load_config(args.config), args.output, args.app_root)
    except (ValueError, RuntimeError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps({"output": str(args.output / "benchmark_summary.json"), "aggregate": payload["aggregate"]}, indent=2))
    if not payload["aggregate"]["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
