from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

from app.main import app
from benchmarks.metrics import summarize_samples, write_json
from benchmarks.oracle import validate_create_response, validate_list_response, validate_update_response
from benchmarks.reset import reset_database
from benchmarks.workload import build_workload


def load_config(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data


def run_once(seed: int = 7, note_count: int = 20) -> dict[str, Any]:
    client = TestClient(app)
    reset_database(seed=seed, count=note_count)
    trace = build_workload(seed=seed, note_count=note_count)
    samples: list[float] = []
    results: list[dict[str, Any]] = []

    for step in trace:
        name = step["name"]
        start = time.perf_counter()
        if step["method"] == "GET":
            response = client.get(step["path"], params=step.get("params", {}))
        elif step["method"] == "POST":
            response = client.post(step["path"], json=step.get("payload", {}))
        elif step["method"] == "PUT":
            response = client.put(step["path"], json=step.get("payload", {}))
        elif step["method"] == "DELETE":
            response = client.delete(step["path"])
        else:
            raise ValueError(f"Unsupported method: {step['method']}")
        elapsed_ms = (time.perf_counter() - start) * 1000
        samples.append(elapsed_ms)

        result = {
            "name": name,
            "status_code": response.status_code,
            "elapsed_ms": elapsed_ms,
            "ok": response.status_code < 400,
        }
        payload = response.json() if response.content else {}
        if name == "list_initial":
            result["valid"] = validate_list_response(payload, step["expected_total"], step.get("expected_titles"))
        elif name == "create_note":
            result["valid"] = validate_create_response(payload, step["expected_title"], step["expected_body"])
        elif name == "search_notes":
            result["valid"] = validate_list_response(payload, step["expected_total"], step.get("expected_titles"))
        elif name == "update_note":
            result["valid"] = validate_update_response(payload, step["expected_title"], step["expected_body"])
        elif name == "delete_note":
            result["valid"] = response.status_code == step["expected_status"]

        results.append(result)

    return {
        "seed": seed,
        "note_count": note_count,
        "samples": samples,
        "per_operation": results,
        "summary": summarize_samples(samples),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the notes app")
    parser.add_argument("--config", required=True, help="Path to YAML benchmark config")
    parser.add_argument("--output", default="tmp", help="Directory for output JSON (default: tmp)")
    args = parser.parse_args()

    config = load_config(args.config)
    repetitions = int(config.get("repetitions", 1))
    seed = int(config.get("seed", 7))
    note_count = int(config.get("note_count", 20))
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_results = []
    all_samples: list[float] = []
    for index in range(repetitions):
        outcome = run_once(seed=seed, note_count=note_count)
        run_results.append({"run_index": index, **outcome})
        all_samples.extend(outcome["samples"])

    payload = {
        "config": config,
        "runs": run_results,
        "aggregate": summarize_samples(all_samples),
    }

    output_path = output_dir / "benchmark_summary.json"
    write_json(output_path, payload)
    print(json.dumps({"output": str(output_path), "aggregate": payload["aggregate"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
