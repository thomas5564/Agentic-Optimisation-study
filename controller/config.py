from __future__ import annotations

import math
from pathlib import Path
from typing import Literal
import yaml
from pydantic import Field, model_validator

from agents.schemas import StrictModel
from benchmarks.config import BenchmarkConfig


class ExperimentConfig(StrictModel):
    schema_version: Literal[1] = 1
    phase: Literal["smoke", "pilot", "final"] = "smoke"
    epsilon: float = Field(ge=0, lt=1)
    benchmark: dict
    baseline: str = "research/baseline"
    role_timeout_seconds: float = Field(default=120.0, gt=0)
    evaluation_timeout_seconds: float = Field(default=180.0, gt=0)
    max_input_bytes: int = Field(default=200000, gt=0)
    max_output_bytes: int = Field(default=1000000, gt=0)
    max_tool_calls: int = Field(default=30, ge=0)
    repair_budget: Literal[0] = 0
    role_retries: Literal[0] = 0
    checkpoints: list[int] = Field(default_factory=lambda: [10, 15, 20, 25, 30])
    mock_cases: list[str] = Field(default_factory=lambda: ["noop"])
    model: str | None = None
    reasoning: str = "medium"
    image: str | None = None
    agent_network: str = "bridge"
    replicates: int = Field(default=3, ge=1)
    pilot_record: str | None = None
    input_token_limit: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_settings(self):
        try:
            BenchmarkConfig(**self.benchmark)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid benchmark configuration: {error}") from error
        for name in ("epsilon", "role_timeout_seconds", "evaluation_timeout_seconds"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite")
        if not self.mock_cases or any(x not in {"noop", "comment", "faster", "slower", "broken", "malformed", "timeout", "audit_failure", "forbidden"} for x in self.mock_cases):
            raise ValueError("Unknown or empty mock_cases")
        if sorted(set(self.checkpoints)) != self.checkpoints or any(n <= 0 for n in self.checkpoints):
            raise ValueError("checkpoints must be unique positive sorted integers")
        if self.phase == "final":
            if not self.model or not self.image or not self.image.startswith("sha256:"):
                raise ValueError("Final runs require explicit model and immutable image ID")
            if not self.pilot_record or self.replicates < 3 or not self.input_token_limit:
                raise ValueError("Final runs require pilot_record, >=3 replicates, and input_token_limit")
            if self.checkpoints != [10, 15, 20, 25, 30]:
                raise ValueError("Final checkpoints must be 10,15,20,25,30")
        return self


def load_config(path: str | Path) -> ExperimentConfig:
    data = yaml.safe_load(Path(path).read_text())
    return ExperimentConfig.model_validate(data)
