from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, median
from typing import Any


def summarize_samples(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {"mean": 0.0, "median": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0}

    ordered = sorted(samples)
    pct95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95)))
    return {
        "mean": float(mean(samples)),
        "median": float(median(samples)),
        "p95": float(ordered[pct95_index]),
        "min": float(min(samples)),
        "max": float(max(samples)),
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return destination
