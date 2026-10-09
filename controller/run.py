from __future__ import annotations

import argparse
import json
from pathlib import Path

from agents.codex import CodexBackend
from agents.mock import MockBackend
from controller.config import load_config
from controller.engine import Engine, initialize_run
from controller.evaluation import Evaluator
from controller.storage import run_lock


def main():
    parser = argparse.ArgumentParser(description="Run a journaled optimization experiment")
    parser.add_argument("--backend", choices=["mock", "codex"], required=True)
    parser.add_argument("--condition", choices=["stateless", "memory"], required=True)
    parser.add_argument("--iterations", type=int, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        backend = MockBackend() if args.backend == "mock" else CodexBackend(config)
        preflight = backend.preflight() if args.backend == "codex" else None
        with run_lock(args.output):
            initialize_run(args.output, config, args.backend, args.condition, args.iterations, preflight=preflight)
        engine = Engine(args.output, backend, Evaluator(config, isolated=args.backend == "codex"))
        state = engine.run()
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(state, indent=2))
    if state["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
