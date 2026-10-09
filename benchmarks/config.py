from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import math

import yaml


@dataclass(frozen=True)
class BenchmarkConfig:
    seed: int = 7
    note_count: int = 100
    cycles: int = 20
    repetitions: int = 5
    warmups: int = 2
    timeout_seconds: float = 5.0
    startup_timeout_seconds: float = 15.0
    concurrency: int = 1

    def __post_init__(self):
        for name in ("note_count", "cycles", "repetitions", "warmups", "concurrency"):
            value = getattr(self, name)
            minimum = 0 if name == "warmups" else 1
            if type(value) is not int or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        if type(self.seed) is not int:
            raise ValueError("seed must be an integer")
        if self.concurrency != 1:
            raise ValueError("Only concurrency=1 is supported")
        for name in ("timeout_seconds", "startup_timeout_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")

    def to_dict(self):
        return asdict(self)


def load_config(path: str | Path) -> BenchmarkConfig:
    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a YAML mapping")
    unknown = set(data) - set(BenchmarkConfig.__dataclass_fields__)
    if unknown:
        raise ValueError(f"Unsupported config fields: {sorted(unknown)}")
    return BenchmarkConfig(**data)
