from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
from pathlib import Path

import yaml

from benchmarks.run import run_once


def load_config(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile the notes benchmark workload")
    parser.add_argument("--config", required=True, help="Path to YAML benchmark config")
    parser.add_argument("--output", default="tmp", help="Directory for profile output (default: tmp)")
    args = parser.parse_args()

    config = load_config(args.config)
    seed = int(config.get("seed", 7))
    note_count = int(config.get("note_count", 20))
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    profiler = cProfile.Profile()
    profiler.enable()
    run_once(seed=seed, note_count=note_count)
    profiler.disable()

    buffer = io.StringIO()
    stats = pstats.Stats(profiler, stream=buffer).sort_stats("cumulative")
    stats.print_stats(20)
    profile_text = buffer.getvalue()

    output_path = output_dir / "profile.txt"
    output_path.write_text(profile_text, encoding="utf-8")
    print(json.dumps({"output": str(output_path), "seed": seed, "note_count": note_count}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
