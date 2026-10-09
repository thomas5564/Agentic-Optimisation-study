"""Trusted evaluation worker; candidate roots and official tests are separate inputs."""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import pstats
import sys

from benchmarks.config import BenchmarkConfig
from benchmarks.metrics import aggregate_runs, write_json
from benchmarks.run import run_once, environment
from benchmarks.runtime import candidate_server


def validate(root: Path, output: Path, config: BenchmarkConfig) -> dict:
    for path in sorted((root / "app").rglob("*.py")):
        try:
            compile(path.read_text(), str(path), "exec")
        except (SyntaxError, UnicodeError) as error:
            return {"correct": False, "status": "syntax_failed", "detail": str(error)}
    try:
        with candidate_server(root, config, output / "startup.log"):
            pass
    except (RuntimeError, TimeoutError, ValueError) as error:
        return {"correct": False, "status": "startup_failed", "detail": str(error)}
    import pytest
    # Tests talk to candidate HTTP processes. Do not import candidate code into pytest.
    os.environ["NOTES_EVALUATION_ROOT"] = str(root)
    captured = io.StringIO()
    # Test paths/contracts are supplied by the trusted evaluator, never by the patch.
    with redirect_stdout(captured), redirect_stderr(captured):
        code = pytest.main([str(root / "tests" / "test_notes.py"), "-q", "-c", "/dev/null",
                            "--rootdir", str(root), "-p", "no:cacheprovider"])
    (output / "tests.txt").write_text(captured.getvalue())
    if int(code) in (2, 3, 4, 5):
        return {"correct": False, "status": "infrastructure_error", "detail": f"pytest could not complete: {int(code)}"}
    return {"correct": int(code) == 0, "status": "passed" if int(code) == 0 else "correctness_failed", "exit_code": int(code)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--operation", choices=["validate", "measure", "profile"], required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    config = BenchmarkConfig(**json.loads(args.config.read_text()))
    if args.operation == "validate":
        result = validate(args.root, args.output, config)
    elif args.operation == "measure":
        runs = []
        for i in range(config.repetitions):
            run = run_once(config, args.root, args.output / f"server-{i}.log")
            runs.append(run)
            write_json(args.output / "repetitions" / f"{i:03d}.json", run)
            result = {"schema_version": 1, "synthetic": False, "complete": i + 1 == config.repetitions,
                      "runs": runs, "aggregate": aggregate_runs(runs)}
            write_json(args.output / "result.json", result)
    else:
        raw = args.output / "application.prof"
        run = run_once(config, args.root, args.output / "server.log", raw)
        valid = not run["error"] and run.get("counts", {}).get("failed", 1) == 0 and raw.exists()
        text = None
        if valid:
            stream = io.StringIO()
            pstats.Stats(str(raw), stream=stream).sort_stats("cumulative").print_stats(40)
            text = stream.getvalue().replace(str(args.root), "/workspace")
            (args.output / "profile.txt").write_text(text)
        result = {"schema_version": 1, "valid": valid, "text": text, "score_ms": None, "run": run}
    result["environment"] = environment()
    write_json(args.output / "result.json", result)


if __name__ == "__main__":
    main()
