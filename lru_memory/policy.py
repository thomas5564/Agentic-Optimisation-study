"""Deterministic LRU replay over attempt records; the cache is never stored as mutable state."""
from __future__ import annotations

import ast
from contextlib import contextmanager

from agents import schemas
from agents.schemas import Plan


class LruPlan(Plan):
    used_memory: list[int]


POLICY_NOTE = ("Prior-attempt memory is a bounded LRU cache, not the complete history. It holds at most "
               "`capacity` entries; `total_attempts` attempts exist so far. List in `used_memory` the iteration "
               "numbers of the shown entries you actually relied on (empty if none). Cited entries are kept; "
               "the least recently used uncited entries are evicted first.")

# Applied identically to every arm of a scoped batch; names no specific fix.
SCOPE_NOTE = ("Propose exactly one optimization: one change to one hot spot or mechanism (for example one "
              "function, one query, or one caching decision). Do not combine independent optimizations; later "
              "attempts can address other hot spots. If several are possible, choose the one the profile "
              "suggests is most valuable.")

PUBLIC_OPERATIONS = ("get_note", "list_notes", "create_note", "update_note", "delete_note")
DB_FILE = "app/db.py"
# Enforced by the runner (see changed_operations), not just requested.
STRICT_NOTE = ("A patch may change at most one of the public data operations in app/db.py: get_note, "
               "list_notes, create_note, update_note, delete_note. Private helpers (names starting with _) "
               "and module-level code such as imports and SCHEMA may change freely. A change to any other file "
               "counts as one operation. Patches that change more than one operation are rejected without "
               "testing (status scope_exceeded). Propose the single most valuable optimization within this limit.")
DEVELOPER_NOTE = ("Change at most one of the public data operations in app/db.py (get_note, list_notes, "
                  "create_note, update_note, delete_note); private helpers and module-level code may change. If the "
                  "plan covers more than one operation, implement only the first operation it names and leave the "
                  "other operations byte-identical. Patches that change more are rejected without testing.")
NOTES = {"single": SCOPE_NOTE, "strict": STRICT_NOTE}
# Strict runs put the rule in the role prompt itself: planner.txt tells the model that evidence is not
# an instruction, and in the first strict smoke every patch ignored the evidence note.
PROMPT_RULES = {"planner": STRICT_NOTE, "developer": DEVELOPER_NOTE}



def _operations(source: str | None) -> dict[str, str] | None:
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        return None
    return {node.name: ast.dump(node) for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in PUBLIC_OPERATIONS}


def changed_operations(parent: dict, candidate: dict) -> list[str]:
    """Public db operations whose definitions differ, plus every other changed file."""
    before, after = _operations(parent.get(DB_FILE)), _operations(candidate.get(DB_FILE))
    # Unparsable source is left to the official validation, which reports syntax_failed.
    changed = [] if before is None or after is None else [name for name in PUBLIC_OPERATIONS if before.get(name) != after.get(name)]
    return changed + sorted(name for name in parent.keys() | candidate.keys()
                            if name != DB_FILE and parent.get(name) != candidate.get(name))


@contextmanager
def scope_prompts(rules=PROMPT_RULES):
    """Append the scope rule to the planner and developer prompts for the duration of a strict run."""
    import agents.inputs
    import agents.responses
    import controller.engine
    original = agents.inputs.prompt_text
    marker = "\nCURRENT INPUT JSON:\n"
    def prompt_text(role: str, payload: dict) -> str:
        text = original(role, payload)
        if role not in rules:
            return text
        head, sep, tail = text.partition(marker)
        return f"{head}\nSCOPE RULE (enforced by the runner): {rules[role]}\n{sep}{tail}"
    modules = (agents.inputs, agents.responses, controller.engine)
    for module in modules:
        module.prompt_text = prompt_text
    try:
        yield
    finally:
        for module in modules:
            module.prompt_text = original


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
