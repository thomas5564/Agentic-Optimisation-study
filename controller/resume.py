from __future__ import annotations

import argparse
import json
from pathlib import Path

from agents.codex import CodexBackend
from agents.mock import MockBackend
from controller.config import ExperimentConfig
from controller.engine import Engine
from controller.evaluation import Evaluator
from controller.journal import Journal
from controller.storage import read_json, run_lock


def main():
    parser = argparse.ArgumentParser(description="Resume recorded stages without repeating completed role calls")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--abandon-call", help="Explicitly mark an unresolved call failed, e.g. 001-developer; never retries it")
    parser.add_argument("--recover-call", help="Recover an archived complete role result after a crash before journal commit")
    args = parser.parse_args()
    if args.abandon_call and args.recover_call:
        parser.error("Choose recover-call or abandon-call, not both")
    try:
        manifest = read_json(args.run_dir / "manifest.json")
        config = ExperimentConfig.model_validate(manifest["config"])
        backend = MockBackend() if manifest["backend"] == "mock" else CodexBackend(config)
        if manifest["backend"] == "codex":
            evidence = backend.preflight()
            if evidence != manifest["preflight"]:
                raise ValueError("Live backend changed since run creation")
        if args.abandon_call:
            with run_lock(args.run_dir):
                Journal(args.run_dir).abandon_call(args.abandon_call)
        if args.recover_call:
            with run_lock(args.run_dir):
                Journal(args.run_dir).recover_call(args.recover_call)
        state = Engine(args.run_dir, backend, Evaluator(config, isolated=manifest["backend"] == "codex")).run()
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(state, indent=2))
    if state["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
