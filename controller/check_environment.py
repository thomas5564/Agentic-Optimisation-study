"""Unpaid container integration: CLI/isolation probe and real baseline evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agents.codex import inspect_cli
from agents.preflight import isolation_probe
from benchmarks.metrics import write_json
from benchmarks.runtime import PROJECT_ROOT
from controller.config import load_config
from controller.evaluation import Evaluator
from controller.storage import load_baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a fresh integration output directory")
    args.output.mkdir(parents=True)
    try:
        config = load_config(args.config)
        evidence = {"schema_version":1, "live_model_calls":0, "cli":inspect_cli(config), "isolation":isolation_probe(config)}
        write_json(args.output / "preflight.json", evidence)
        directory = Path(config.baseline)
        files = load_baseline(directory if directory.is_absolute() else PROJECT_ROOT / directory)
        evaluator = Evaluator(config, isolated=True)
        evidence["validation"] = evaluator.validate(files, args.output / "validation")
        evidence["measurement"] = evaluator.measure(files, args.output / "measurement")
        evidence["profile"] = evaluator.profile(files, args.output / "profile")
        evidence["passed"] = bool(evidence["validation"].get("correct") and evidence["measurement"]["aggregate"]["valid"] and evidence["profile"]["valid"])
        write_json(args.output / "integration.json", evidence)
    except (ValueError, RuntimeError, OSError) as error:
        write_json(args.output / "failure.json", {"error":str(error)})
        parser.exit(2,f"{error}\n")
    print(json.dumps({"passed":evidence["passed"],"output":str(args.output),"live_model_calls":0},indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
