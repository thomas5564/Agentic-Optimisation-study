"""LRU arm built on the unmodified controller.

An LRU run is recorded by the existing controller as condition "memory"; the sidecar
`lru.json` (written before the manifest) marks it as LRU and archives this package's source.
Resume LRU runs only with `lru_memory.resume`; `controller.resume` would continue them with
complete memory.
"""
from __future__ import annotations

from pathlib import Path

from agents.mock import MockBackend
from agents.factory import make_backend
from benchmarks.metrics import write_json
from benchmarks.run import content_hash
from benchmarks.runtime import PROJECT_ROOT
from controller.engine import Engine, initialize_run
from controller.storage import read_json
from lru_memory.policy import POLICY_NOTE, planner_schema, replay

SOURCE = Path(__file__).parent
ARMS = ("stateless", "memory", "memory_lru")


def lru_source() -> dict:
    return {p.name: p.read_text() for p in sorted(SOURCE.glob("*.py"))}


def is_lru(root: Path) -> bool:
    return (root / "lru.json").exists()


def initialize_lru_run(root: Path, config, backend_name: str, iterations: int, capacity: int, **kwargs) -> dict:
    if config.phase == "final":
        raise ValueError("The frozen final protocol covers only stateless and memory; freeze a new three-arm config first")
    if type(capacity) is not int or capacity < 1:
        raise ValueError("LRU capacity must be a positive integer")
    if root.resolve().is_relative_to(PROJECT_ROOT):
        raise ValueError("Run artifacts must live outside the development repository")
    if (root / "manifest.json").exists():
        raise ValueError("Run already exists; use lru_memory.resume")
    source = lru_source()
    # Sidecar first: a crash before the manifest leaves no run that could pass as full memory.
    write_json(root / "lru.json", {"schema_version": 1, "policy": "lru", "capacity": capacity,
                                   "source": source, "source_hash": content_hash(source)})
    return initialize_run(root, config, backend_name, "memory", iterations, **kwargs)


def initialize_arm(root: Path, config, backend_name: str, arm: str, iterations: int, capacity: int | None, **kwargs) -> dict:
    if arm == "memory_lru":
        return initialize_lru_run(root, config, backend_name, iterations, capacity, **kwargs)
    if arm not in ARMS:
        raise ValueError(f"Unknown arm {arm}")
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


class LruEngine(Engine):
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
    return (LruEngine if is_lru(root) else Engine)(root, backend, evaluator)
