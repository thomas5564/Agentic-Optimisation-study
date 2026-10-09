from __future__ import annotations

import json
from pathlib import Path
from agents.schemas import RoleInput
from benchmarks.run import content_hash

PROMPTS = Path(__file__).parent / "prompts"
OBJECTIVE = "Reduce median-of-repetition mean request latency while preserving the complete notes API contract and durability."


class ContextLimit(RuntimeError):
    pass


def build_input(role: str, *, evidence: dict, memory: list[dict] | None = None,
                plan: dict | None = None, patch: list[dict] | None = None, decision: dict | None = None) -> dict:
    if role != "planner" and memory is not None:
        raise ValueError("Only Planner may receive history")
    result = RoleInput(role=role, objective=OBJECTIVE, evidence=evidence, plan=plan,
                       patch=patch, decision=decision, memory=memory,
                       memory_count=len(memory) if memory is not None else 0,
                       memory_hash=content_hash(memory) if memory is not None else None)
    return result.model_dump()


def prompt_text(role: str, payload: dict) -> str:
    return (PROMPTS / f"{role}.txt").read_text() + "\nCURRENT INPUT JSON:\n" + json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def check_context(role: str, payload: dict, files: dict, config):
    size = len(prompt_text(role, payload).encode()) + sum(len(v.encode()) for v in files.values())
    # Byte count is a conservative input admission budget, NOT measured token usage.
    limit = min(config.max_input_bytes, config.input_token_limit or config.max_input_bytes)
    if size > limit:
        raise ContextLimit(f"Complete role input requires {size} bytes; configured conservative admission budget is {limit}. No history was dropped.")
    return size
