from __future__ import annotations

from typing import Literal, Protocol
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Plan(StrictModel):
    schema_version: Literal[1]
    hypothesis: str = Field(min_length=1, max_length=4000)
    change: str = Field(min_length=1, max_length=4000)
    risks: list[str]
    approach: Literal["query", "index", "cache", "serialization", "computation", "other"]


class Edit(StrictModel):
    path: str
    content: str | None


class Development(StrictModel):
    schema_version: Literal[1]
    summary: str
    edits: list[Edit]


class Audit(StrictModel):
    schema_version: Literal[1]
    interpretation: str = Field(max_length=4000)
    limitations: list[str]


OUTPUTS = {"planner": Plan, "developer": Development, "auditor": Audit}


class RoleInput(StrictModel):
    schema_version: Literal[1] = 1
    role: Literal["planner", "developer", "auditor"]
    objective: str
    evidence: dict
    plan: dict | None = None
    patch: list[dict] | None = None
    decision: dict | None = None
    memory: list[dict] | None = None
    memory_count: int = 0
    memory_hash: str | None = None


class RoleResult(StrictModel):
    schema_version: Literal[1] = 1
    status: Literal["ok", "timeout", "malformed", "agent_error", "interrupted_unknown", "context_limit"]
    output: dict | None = None
    usage: dict | None = None
    elapsed_seconds: float | None = None
    exit_code: int | None = None
    error: str | None = None
    metadata: dict = Field(default_factory=dict)


class Backend(Protocol):
    def invoke(self, role: str, payload: dict, workspace: Path, artifacts: Path,
               case: str = "noop") -> RoleResult: ...
