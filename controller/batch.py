"""Serial paired runs with alternating condition order and fixed paired seeds."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agents.codex import CodexBackend
from agents.mock import MockBackend
from benchmarks.metrics import write_json
from benchmarks.run import content_hash
from controller.config import load_config
from controller.engine import Engine, initialize_run
from controller.evaluation import Evaluator
from controller.storage import read_json, run_lock


def run_batch(config, backend_name: str, iterations: int, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "batch.json"
    schedule = [{"pair_id": str(pair), "condition": condition, "seed": config.benchmark.get("seed", 7),
                 "directory": f"pair-{pair:02d}-{condition}"}
                for pair in range(config.replicates)
                for condition in (("stateless", "memory") if pair % 2 == 0 else ("memory", "stateless"))]
    batch = {"schema_version": 1, "config_hash": content_hash(config.model_dump()), "backend": backend_name,
             "iterations": iterations, "schedule": schedule}
    with run_lock(output):
        if manifest_path.exists() and read_json(manifest_path) != batch:
            raise ValueError("Batch protocol changed; use a new output directory")
        write_json(manifest_path, batch)
        states = []
        for entry in schedule:
            settings = config.model_copy(update={"benchmark": {**config.benchmark, "seed": entry["seed"]}})
            backend = MockBackend() if backend_name == "mock" else CodexBackend(settings)
            preflight = backend.preflight() if backend_name == "codex" else None
            root = output / entry["directory"]
            with run_lock(root):
                if not (root / "manifest.json").exists():
                    initialize_run(root, settings, backend_name, entry["condition"], iterations,
                                   pair_id=entry["pair_id"], preflight=preflight)
                else:
                    existing = read_json(root / "manifest.json")
                    if existing["config_hash"] != content_hash(settings.model_dump()) or existing["preflight"] != preflight:
                        raise ValueError("Saved batch run configuration/backend differs")
            state = Engine(root, backend, Evaluator(settings, isolated=backend_name == "codex")).run()
            states.append({**entry, **state})
            write_json(output / "batch-status.json", {"runs": states, "complete": len(states) == len(schedule) and all(s["status"] == "complete" for s in states)})
            if state["status"] != "complete":
                break
    return states


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["mock", "codex"], required=True)
    parser.add_argument("--iterations", type=int, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        states = run_batch(load_config(args.config), args.backend, args.iterations, args.output)
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(states, indent=2))
    if any(s["status"] != "complete" for s in states):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
