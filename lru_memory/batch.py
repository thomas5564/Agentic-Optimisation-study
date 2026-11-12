"""Serial three-arm replicates (stateless, memory, memory_lru) with rotating order and fixed seeds."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.metrics import write_json
from benchmarks.run import content_hash
from controller.config import load_config
from controller.evaluation import Evaluator
from controller.storage import read_json, run_lock
from lru_memory.engine import ARMS, engine_for, initialize_arm, is_lru, make_arm_backend


def schedule(replicates: int, seed: int) -> list[dict]:
    return [{"pair_id": str(rep), "condition": arm, "seed": seed, "directory": f"rep-{rep:02d}-{arm}"}
            for rep in range(replicates)
            for arm in ARMS[rep % len(ARMS):] + ARMS[:rep % len(ARMS)]]


def run_batch(config, backend_name: str, iterations: int, capacity: int, output: Path):
    if config.phase == "final":
        raise ValueError("The frozen final protocol covers only stateless and memory; freeze a new three-arm config first")
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "batch.json"
    batch = {"schema_version": 1, "arms": list(ARMS), "lru_capacity": capacity,
             "config_hash": content_hash(config.model_dump()), "backend": backend_name, "iterations": iterations,
             "schedule": schedule(config.replicates, config.benchmark.get("seed", 7))}
    with run_lock(output):
        if manifest_path.exists() and read_json(manifest_path) != batch:
            raise ValueError("Batch protocol changed; use a new output directory")
        write_json(manifest_path, batch)
        states = []
        for entry in batch["schedule"]:
            settings = config.model_copy(update={"benchmark": {**config.benchmark, "seed": entry["seed"]}})
            arm = entry["condition"]
            backend = make_arm_backend(backend_name, settings, arm)
            preflight = backend.preflight() if backend_name != "mock" else None
            root = output / entry["directory"]
            with run_lock(root):
                if not (root / "manifest.json").exists():
                    initialize_arm(root, settings, backend_name, arm, iterations,
                                   capacity if arm == "memory_lru" else None,
                                   pair_id=entry["pair_id"], preflight=preflight)
                else:
                    existing = read_json(root / "manifest.json")
                    if (existing["config_hash"] != content_hash(settings.model_dump()) or existing["preflight"] != preflight
                            or is_lru(root) != (arm == "memory_lru")):
                        raise ValueError("Saved batch run configuration/backend differs")
            state = engine_for(root, backend, Evaluator(settings, isolated=backend_name != "mock")).run()
            states.append({**entry, **state})
            write_json(output / "batch-status.json", {"runs": states, "complete": len(states) == len(batch["schedule"]) and all(s["status"] == "complete" for s in states)})
            if state["status"] != "complete":
                break
    return states


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["mock", "codex", "responses", "chat"], required=True)
    parser.add_argument("--iterations", type=int, required=True)
    parser.add_argument("--capacity", type=int, required=True, help="LRU entry capacity K for the memory_lru arm")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        states = run_batch(load_config(args.config), args.backend, args.iterations, args.capacity, args.output)
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(states, indent=2))
    if any(s["status"] != "complete" for s in states):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
