"""LRU arm built on the unmodified controller.

An LRU run is recorded by the existing controller as condition "memory"; the sidecar
`lru.json` (written before the manifest) marks it as LRU and archives this package's source.
Resume LRU runs only with `lru_memory.resume`; `controller.resume` would continue them with
complete memory.
"""
from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

from agents.mock import MockBackend
from agents.factory import make_backend
from benchmarks.metrics import write_json
from benchmarks.run import content_hash
from benchmarks.runtime import PROJECT_ROOT
from controller.engine import Engine, initialize_run
from controller.storage import read_json
from lru_memory.policy import DEVELOPER_NOTE, NOTES, POLICY_NOTE, changed_operations, planner_schema, replay, scope_prompts

SOURCE = Path(__file__).parent
ARMS = ("stateless", "memory", "memory_lru")


def lru_source() -> dict:
    return {p.name: p.read_text() for p in sorted(SOURCE.glob("*.py"))}


def is_lru(root: Path) -> bool:
    return (root / "lru.json").exists()


def is_scoped(root: Path) -> bool:
    return (root / "scope.json").exists()


def check_new_run(root: Path):
    if root.resolve().is_relative_to(PROJECT_ROOT):
        raise ValueError("Run artifacts must live outside the development repository")
    if (root / "manifest.json").exists():
        raise ValueError("Run already exists; use lru_memory.resume")


def write_scope(root: Path, scope: str | None):
    if scope is None:
        return
    if scope not in NOTES:
        raise ValueError(f"Unknown scope {scope}")
    check_new_run(root)
    # Sidecar before the manifest, as with lru.json, so a scoped run never looks unscoped.
    write_json(root / "scope.json", {"schema_version": 1, "scope": scope, "note": NOTES[scope],
                                     **({"developer_note": DEVELOPER_NOTE} if scope == "strict" else {})})


def initialize_lru_run(root: Path, config, backend_name: str, iterations: int, capacity: int, scope: str | None = None, **kwargs) -> dict:
    if config.phase == "final":
        raise ValueError("The frozen final protocol covers only stateless and memory; freeze a new three-arm config first")
    if type(capacity) is not int or capacity < 1:
        raise ValueError("LRU capacity must be a positive integer")
    check_new_run(root)
    write_scope(root, scope)
    source = lru_source()
    # Sidecar first: a crash before the manifest leaves no run that could pass as full memory.
    write_json(root / "lru.json", {"schema_version": 1, "policy": "lru", "capacity": capacity,
                                   "source": source, "source_hash": content_hash(source)})
    return initialize_run(root, config, backend_name, "memory", iterations, **kwargs)


def initialize_arm(root: Path, config, backend_name: str, arm: str, iterations: int, capacity: int | None,
                   scope: str | None = None, **kwargs) -> dict:
    if arm == "memory_lru":
        return initialize_lru_run(root, config, backend_name, iterations, capacity, scope, **kwargs)
    if arm not in ARMS:
        raise ValueError(f"Unknown arm {arm}")
    if config.phase == "final" and scope:
        raise ValueError("The frozen final protocol has no scope rule; freeze a new three-arm config first")
    write_scope(root, scope)
    return initialize_run(root, config, backend_name, arm, iterations, **kwargs)


class LruMockBackend(MockBackend):
    """Mock fixture: cites the earliest shown entry so refresh and eviction are exercised."""
    def invoke(self, role, payload, workspace, artifacts, case="noop"):
        result = super().invoke(role, payload, workspace, artifacts, case)
        policy = payload["evidence"].get("memory_policy")
        if role == "planner" and policy and result.status == "ok" and "hypothesis" in result.output:
            result.output = {**result.output, "used_memory": policy["shown_iterations"][:1]}
        return result


def make_arm_backend(name: str, config, arm: str):
    return LruMockBackend() if name == "mock" and arm == "memory_lru" else make_backend(name, config)


class ArmEngine(Engine):
    """Adds the optional scope note to Planner evidence and, for the strict scope, rejects patches that
    change more than one public data operation before they are tested. Otherwise the unmodified engine."""
    def __init__(self, root: Path, backend, evaluator, crash_hook=None):
        super().__init__(root, backend, evaluator, crash_hook)
        self.scope = read_json(self.root / "scope.json") if is_scoped(self.root) else None
        self.parent_files = None

    def verify(self):
        super().verify()
        if self.scope and (self.scope["note"] != NOTES.get(self.scope["scope"])
                           or self.scope.get("developer_note") != (DEVELOPER_NOTE if self.strict else None)):
            raise ValueError("Scope note changed since run creation; resume requires the recorded note")

    @property
    def strict(self) -> bool:
        return bool(self.scope) and self.scope["scope"] == "strict"

    def run(self) -> dict:
        with scope_prompts() if self.strict else nullcontext():
            return super().run()

    def evaluation(self, key: str, operation: str, files: dict, required: bool = False):
        if operation == "validate" and not required and self.strict:
            changed = changed_operations(self.parent_files, files)
            if len(changed) > 1:
                return {"correct": False, "status": "scope_exceeded", "detail": f"Changed {len(changed)} operations: {', '.join(changed)}"}
        return super().evaluation(key, operation, files, required)

    def ask(self, iteration: int, role: str, payload: dict, files: dict, case: str) -> dict:
        if role == "developer":
            self.parent_files = files  # the parent the Developer edits; checked against its candidate
        if role == "planner" and self.scope:
            payload = {**payload, "evidence": {**payload["evidence"], "scope_policy": {k: self.scope[k] for k in ("scope", "note")}}}
        return super().ask(iteration, role, payload, files, case)


class LruEngine(ArmEngine):
    def __init__(self, root: Path, backend, evaluator, crash_hook=None):
        super().__init__(root, backend, evaluator, crash_hook)
        self.lru = read_json(self.root / "lru.json")
        self.capacity = self.lru["capacity"]
        self.policy = None

    def verify(self):
        super().verify()
        if self.manifest["condition"] != "memory":
            raise ValueError("LRU runs are recorded as the memory condition")
        if content_hash(self.lru["source"]) != self.lru["source_hash"]:
            raise ValueError("Archived LRU source changed")
        if self.lru["source"] != lru_source():
            raise ValueError("lru_memory source changed since run creation; resume requires the recorded implementation")

    def run(self) -> dict:
        with planner_schema():
            return super().run()

    def run_iteration(self, index: int, parent_hash: str, prior: list[dict]) -> dict:
        steps = replay(prior, self.capacity)
        order = steps[-1]["order_after"] if steps else []
        shown = sorted(order)
        write_json(self.root / "lru" / f"{index:03d}.json", {"schema_version": 1, "iteration": index,
                   "capacity": self.capacity, "total_attempts": len(prior), "order_before": order, "shown": shown})
        self.policy = {"type": "lru", "capacity": self.capacity, "total_attempts": len(prior),
                       "shown_iterations": shown, "note": POLICY_NOTE}
        try:
            # The newest attempt is always most recently used, so prior[-1] stays the latest attempt.
            return super().run_iteration(index, parent_hash, [prior[i - 1] for i in shown])
        finally:
            self.policy = None

    def ask(self, iteration: int, role: str, payload: dict, files: dict, case: str) -> dict:
        if role == "planner" and self.policy is not None:
            payload = {**payload, "evidence": {**payload["evidence"], "memory_policy": self.policy}}
        return super().ask(iteration, role, payload, files, case)

    def materialize(self, attempts: list[dict]):
        # memory.json keeps the complete log; the cache is a replayed view of it.
        super().materialize(attempts)
        steps = replay(attempts, self.capacity)
        write_json(self.root / "lru-state.json", {"schema_version": 1, "capacity": self.capacity,
                   "order": steps[-1]["order_after"] if steps else [], "steps": steps})


def engine_for(root: Path, backend, evaluator):
    return (LruEngine if is_lru(root) else ArmEngine if is_scoped(root) else Engine)(root, backend, evaluator)
