from __future__ import annotations

import argparse
import json
from pathlib import Path

from controller.config import load_config
from controller.evaluation import Evaluator
from controller.storage import run_lock
from lru_memory.engine import ARMS, engine_for, initialize_arm, make_arm_backend


def main():
    parser = argparse.ArgumentParser(description="Run one arm of the three-arm (stateless/memory/memory_lru) experiment")
    parser.add_argument("--backend", choices=["mock", "codex", "responses", "chat"], required=True)
    parser.add_argument("--condition", choices=ARMS, required=True)
    parser.add_argument("--capacity", type=int, help="LRU entry capacity K (memory_lru only)")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--single-change", action="store_const", dest="scope", const="single", help="Tell the Planner to propose exactly one optimization")
    scope.add_argument("--strict-scope", action="store_const", dest="scope", const="strict", help="Reject patches that change more than one public data operation")
    parser.add_argument("--pair-id", help="Replicate id shared by the arms run separately, so the report pairs them")
    parser.add_argument("--iterations", type=int, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (args.capacity is None) != (args.condition != "memory_lru"):
        parser.error("--capacity is required for memory_lru and only valid there")
    try:
        config = load_config(args.config)
        backend = make_arm_backend(args.backend, config, args.condition)
        preflight = backend.preflight() if args.backend != "mock" else None
        with run_lock(args.output):
            initialize_arm(args.output, config, args.backend, args.condition, args.iterations, args.capacity,
                           scope=args.scope, pair_id=args.pair_id, preflight=preflight)
        state = engine_for(args.output, backend, Evaluator(config, isolated=args.backend != "mock")).run()
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(state, indent=2))
    if state["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
