from typing import Literal
from pydantic import Field
from agents.schemas import StrictModel


class Decision(StrictModel):
    accepted: bool
    reason: str
    relative_improvement: float | None = None


class MemoryEntry(StrictModel):
    schema_version: Literal[1] = 1
    iteration: int
    parent_hash: str
    candidate_hash: str | None
    hypothesis: str | None
    attempted_change: str | None
    approach: str | None
    facts: dict
    interpretation: str | None
    limitations: list[str]
    audit_status: str


class Attempt(StrictModel):
    schema_version: Literal[1] = 1
    attempt_id: str
    run_id: str
    iteration: int
    condition: Literal["stateless", "memory"]
    config_hash: str
    parent_hash: str
    candidate_hash: str | None
    retained_hash: str
    status: str
    plan: dict | None
    patch: list[dict]
    validation: dict | None
    parent_measurement: dict | None
    candidate_measurement: dict | None
    retained_score_ms: float | None
    decision: Decision
    audit: dict | None
    audit_status: str
    roles: dict
    memory: MemoryEntry
    synthetic: bool = False
