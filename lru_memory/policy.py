"""Deterministic LRU replay over attempt records; the cache is never stored as mutable state."""
from __future__ import annotations

from contextlib import contextmanager

from agents import schemas
from agents.schemas import Plan


class LruPlan(Plan):
    used_memory: list[int]


POLICY_NOTE = ("Prior-attempt memory is a bounded LRU cache, not the complete history. It holds at most "
               "`capacity` entries; `total_attempts` attempts exist so far. List in `used_memory` the iteration "
               "numbers of the shown entries you actually relied on (empty if none). Cited entries are kept; "
               "the least recently used uncited entries are evicted first.")


def citations(attempt: dict, shown: list[int]) -> dict:
    cited = list(dict.fromkeys(((attempt.get("plan") or {}).get("used_memory")) or []))
    return {"refreshed": [i for i in cited if i in shown], "ignored": [i for i in cited if i not in shown]}


def replay(attempts: list[dict], capacity: int) -> list[dict]:
    """One step per attempt: what that Planner was shown, then citations, insertion and eviction."""
    if capacity < 1:
        raise ValueError("LRU capacity must be at least 1")
    order: list[int] = []
    steps = []
    for attempt in attempts:
        shown = sorted(order)
        cited = citations(attempt, shown)
        for iteration in cited["refreshed"]:
            order.remove(iteration)
            order.append(iteration)
        order.append(attempt["iteration"])
        evicted = order[:-capacity] if len(order) > capacity else []
        order = order[len(evicted):]
        steps.append({"iteration": attempt["iteration"], "shown": shown, **cited,
                      "evicted": evicted, "order_after": list(order)})
    return steps


def lru_view(attempts: list[dict], capacity: int) -> list[int]:
    """Current cache order, least to most recently used."""
    steps = replay(attempts, capacity)
    return steps[-1]["order_after"] if steps else []


@contextmanager
def planner_schema(model=LruPlan):
    """Backends and the journal look up OUTPUTS[role] at call time; swap only for the LRU run."""
    previous = schemas.OUTPUTS["planner"]
    schemas.OUTPUTS["planner"] = model
    try:
        yield
    finally:
        schemas.OUTPUTS["planner"] = previous
