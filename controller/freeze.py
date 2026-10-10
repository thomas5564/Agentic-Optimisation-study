"""Freeze final protocol only after inspecting real, completed paired pilot evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml
from benchmarks.metrics import write_json
from benchmarks.run import content_hash
from controller.config import ExperimentConfig, load_config
from controller.storage import read_json


def freeze(config: ExperimentConfig, pilots: list[Path], output: Path) -> dict:
    if output.exists():
        raise ValueError("Final config already exists; do not overwrite a frozen protocol")
    evidence = []
    conditions = set()
    backends = set()
    noises = []
    for root in pilots:
        manifest = read_json(root / "manifest.json")
        state = read_json(root / "state.json")
        if manifest["phase"] != "pilot" or manifest["backend"] not in {"codex", "responses", "chat"} or manifest["synthetic"] or state["status"] != "complete":
            raise ValueError("Final freezing requires completed real pilot runs")
        for key in ("max_response_tokens", "temperature", "model", "provider_base_url", "provider_key_env", "reasoning", "image", "benchmark", "role_timeout_seconds", "max_tool_calls", "repair_budget", "role_retries"):
            if manifest["config"][key] != config.model_dump()[key]:
                raise ValueError(f"Pilot and proposed final setting differ: {key}; recalibrate before freezing")
        measurement = read_json(root / "journal" / "baseline-measure.json")["result"]
        noise = measurement.get("aggregate", {}).get("noise")
        if not noise or noise.get("relative_range") is None:
            raise ValueError("Pilot lacks repeated baseline noise measurements")
        noises.append(noise["relative_range"])
        conditions.add(manifest["condition"])
        backends.add(manifest["backend"])
        evidence.append({"run_id": manifest["run_id"], "manifest_hash": content_hash(manifest),
                         "baseline_noise": noise, "condition": manifest["condition"]})
    if conditions != {"memory", "stateless"}:
        raise ValueError("Both pilot conditions are required")
    if len(backends) != 1:
        raise ValueError("Pilot conditions must use the same backend")
    if config.epsilon <= max(noises):
        raise ValueError("Final epsilon must be greater than observed baseline relative-range noise")
    record_path = output.with_suffix(".protocol.json").resolve()
    settings = config.model_dump()
    settings.update(phase="final", pilot_record=str(record_path))
    final = ExperimentConfig.model_validate(settings)
    protocol = {"schema_version": 1, "backend":next(iter(backends)), "config_hash": content_hash(final.model_dump()),
                "pilot_evidence": evidence, "max_baseline_relative_range": max(noises), "iterations": 30}
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(record_path, protocol)
    output.write_text(yaml.safe_dump(final.model_dump(), sort_keys=True))
    return protocol


def validate_frozen(config: ExperimentConfig):
    record = read_json(Path(config.pilot_record))
    # Batch seed pairing may vary seeds; the frozen seed is the first pair's seed.
    if record["config_hash"] != content_hash(config.model_dump()):
        raise ValueError("Final config does not match its pre-recorded protocol hash")
    if config.epsilon <= record["max_baseline_relative_range"]:
        raise ValueError("Frozen epsilon does not exceed measured noise")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--pilot-runs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        protocol = freeze(load_config(args.config), args.pilot_runs, args.output)
    except (ValueError, OSError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(protocol, indent=2))


if __name__ == "__main__":
    main()
