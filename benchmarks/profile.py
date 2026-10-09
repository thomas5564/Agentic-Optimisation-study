from __future__ import annotations

import argparse
import io
from pathlib import Path
import pstats

from benchmarks.config import load_config
from benchmarks.metrics import write_json
from benchmarks.run import environment, run_once, source_manifest
from benchmarks.runtime import PROJECT_ROOT, benchmark_lock


def main():
    parser = argparse.ArgumentParser(description="Profile application endpoints separately from timing")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--app-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    config = load_config(args.config)
    args.output.mkdir(parents=True, exist_ok=True)
    raw = args.output / "application.prof"
    if raw.exists():
        parser.error("Profile output already exists; use a fresh output directory")
    with benchmark_lock():
        result = run_once(config, args.app_root, args.output / "server.log", profile=raw)
    summary = {"schema_version": 1, "kind": "profile_only", "score_ms": None,
               "tool": "cProfile", "scope": "endpoint functions, including sync worker threads; excludes ASGI serialization and network",
               "environment": environment(), "config": config.to_dict(),
               "source": source_manifest(args.app_root), "run": result}
    write_json(args.output / "profile_summary.json", summary)
    if result["error"] or not raw.exists() or result.get("counts", {}).get("failed", 1):
        parser.exit(1, "Profiling failed; see profile_summary.json and server.log\n")
    buffer = io.StringIO()
    pstats.Stats(str(raw), stream=buffer).sort_stats("cumulative").print_stats(60)
    (args.output / "profile.txt").write_text(buffer.getvalue())
    print(f"Profile saved to {args.output / 'profile.txt'}; no acceptance score produced")


if __name__ == "__main__":
    main()
