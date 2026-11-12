"""Synthetic timings here are test fixtures, never experiment measurements."""
from copy import deepcopy

import pytest

from agents import schemas
from agents.schemas import Plan
from controller.engine import Engine, implementation_hashes
from controller.storage import read_json
from lru_memory import batch
from lru_memory.engine import LruEngine, LruMockBackend, engine_for, initialize_arm, initialize_lru_run
from lru_memory.policy import LruPlan, lru_view, planner_schema, replay
from lru_memory.report import report
from test_controller import SyntheticEvaluator, config


def attempt(iteration, used=None, plan=True):
    return {"iteration": iteration, "plan": {"used_memory": used or []} if plan else None}


def test_capacity_evicts_least_recently_used():
    assert lru_view([attempt(i) for i in range(1, 6)], 2) == [4, 5]


def test_citation_refresh_changes_eviction_victim():
    attempts = [attempt(1), attempt(2), attempt(3, [1])]
    assert lru_view(attempts, 2) == [1, 3]
    assert replay(attempts, 2)[2]["evicted"] == [2]


def test_unshown_citations_ignored_and_failed_plans_still_inserted():
    steps = replay([attempt(1), attempt(2), attempt(3), attempt(4, [1, 3, 99]), attempt(5, plan=False)], 2)
    assert steps[3]["shown"] == [2, 3]  # 1 was evicted after attempt 3
    assert steps[3]["refreshed"] == [3] and steps[3]["ignored"] == [1, 99]
    assert steps[3]["order_after"] == [3, 4]
    assert steps[4]["refreshed"] == [] and steps[4]["order_after"] == [4, 5]


def test_schema_swap_is_scoped():
    with planner_schema():
        assert schemas.OUTPUTS["planner"] is LruPlan
    assert schemas.OUTPUTS["planner"] is Plan


class RecordingLruBackend(LruMockBackend):
    def __init__(self):
        self.calls = []

    def invoke(self, role, payload, workspace, artifacts, case="noop"):
        self.calls.append((role, deepcopy(payload)))
        result = super().invoke(role, payload, workspace, artifacts, case)
        self.calls[-1] += (deepcopy(result.output),)
        return result


def create(root, iterations=5, capacity=2, cases=None):
    initialize_lru_run(root, config(cases), "mock", iterations, capacity, synthetic=True)
    return LruEngine(root, RecordingLruBackend(), SyntheticEvaluator())


def test_planner_sees_only_cached_entries_and_other_roles_see_none(tmp_path):
    engine = create(tmp_path)
    assert engine.run()["status"] == "complete"
    planners = [(p, out) for role, p, out in engine.backend.calls if role == "planner"]
    # Mock cites the earliest shown entry, so 1 is kept; without citations iteration 5 would see [3, 4].
    assert [[m["iteration"] for m in p["memory"]] for p, _ in planners] == [[], [1], [1, 2], [1, 3], [1, 4]]
    assert [p["memory_count"] for p, _ in planners] == [0, 1, 2, 2, 2]
    assert all(p["evidence"]["memory_policy"]["capacity"] == 2 for p, _ in planners)
    assert [out["used_memory"] for _, out in planners] == [[], [1], [1], [1], [1]]
    assert all(p["memory"] is None for role, p, _ in engine.backend.calls if role != "planner")
    attempts = engine.attempts()
    assert all(a["condition"] == "memory" and "used_memory" in a["plan"] for a in attempts)
    assert read_json(tmp_path / "memory.json")["count"] == 5  # complete log retained
    assert read_json(tmp_path / "lru-state.json")["order"] == [1, 5]
    assert read_json(tmp_path / "lru" / "005.json")["shown"] == [1, 4]
    assert schemas.OUTPUTS["planner"] is Plan


@pytest.mark.parametrize("point", ["after_decision", "before_attempt_commit", "after_attempt_commit", "after_memory_commit"])
def test_resume_replays_same_view_without_duplicate_calls(tmp_path, point):
    engine = create(tmp_path, iterations=3)
    fired = False
    committed = 1 if point in {"after_decision", "before_attempt_commit"} else 2  # crash during iteration 2
    def crash(event):
        nonlocal fired
        if event == point and not fired and len(list((tmp_path / "attempts").glob("*.json"))) == committed:
            fired = True
            raise KeyboardInterrupt("forced interruption")
    engine.crash_hook = crash
    with pytest.raises(KeyboardInterrupt):
        engine.run()
    assert schemas.OUTPUTS["planner"] is Plan
    resumed = engine_for(tmp_path, engine.backend, engine.evaluator)
    assert isinstance(resumed, LruEngine)
    assert resumed.run()["status"] == "complete"
    planners = [p for role, p, _ in engine.backend.calls if role == "planner"]
    assert [[m["iteration"] for m in p["memory"]] for p in planners] == [[], [1], [1, 2]]
    assert read_json(tmp_path / "memory.json")["count"] == 3


def test_lru_source_drift_blocks_resume(tmp_path):
    engine = create(tmp_path, iterations=1)
    lru = read_json(tmp_path / "lru.json")
    lru["source"]["policy.py"] += "\n# drift\n"
    from benchmarks.metrics import write_json
    from benchmarks.run import content_hash
    write_json(tmp_path / "lru.json", {**lru, "source_hash": content_hash(lru["source"])})
    with pytest.raises(ValueError, match="lru_memory source changed"):
        LruEngine(tmp_path, engine.backend, engine.evaluator).run()


def test_bad_capacity_rejected_before_writing(tmp_path):
    with pytest.raises(ValueError, match="capacity"):
        initialize_lru_run(tmp_path, config(), "mock", 1, 0, synthetic=True)
    assert not (tmp_path / "lru.json").exists()


def test_existing_controller_untouched():
    # Adding the package outside controller/agents/benchmarks keeps recorded runs resumable.
    assert not any(name.startswith("lru_memory") for name in implementation_hashes())


def test_batch_rotates_three_arms(tmp_path, monkeypatch):
    seen = []
    class RecordingEngine:
        def __init__(self, root, backend, evaluator):
            self.root, self.manifest = root, read_json(root / "manifest.json")
        def run(self):
            seen.append((self.manifest["pair_id"], self.root.name.split("-", 2)[2], (self.root / "lru.json").exists()))
            return {"status": "complete", "completed_iterations": 3}
    monkeypatch.setattr(batch, "engine_for", RecordingEngine)
    batch.run_batch(config().model_copy(update={"replicates": 3}), "mock", 3, 2, tmp_path)
    assert [(p, arm) for p, arm, _ in seen] == [("0", "stateless"), ("0", "memory"), ("0", "memory_lru"),
                                                 ("1", "memory"), ("1", "memory_lru"), ("1", "stateless"),
                                                 ("2", "memory_lru"), ("2", "stateless"), ("2", "memory")]
    assert all(has_lru == (arm == "memory_lru") for _, arm, has_lru in seen)
    with pytest.raises(ValueError, match="Batch protocol changed"):
        batch.run_batch(config().model_copy(update={"replicates": 3}), "mock", 3, 4, tmp_path)


def test_credentials_wrapper_allowlists_modules_and_passes_arguments(tmp_path, monkeypatch):
    import os
    import sys
    from lru_memory import credentials
    env = tmp_path / "soclaas.env"
    env.write_text("SOCLAAS_BASE_URL=https://example.invalid/v1\nSOCLAAS_API_KEY=fake-test-key\nSOCLAAS_MODEL=default\n")
    for name in ("SOCLAAS_BASE_URL", "SOCLAAS_API_KEY", "SOCLAAS_MODEL"):
        monkeypatch.setenv(name, "")  # restored after the test, so the fake key never leaks
    seen = []
    monkeypatch.setattr(credentials.runpy, "run_module", lambda module, run_name: seen.append((module, list(sys.argv), os.environ["SOCLAAS_API_KEY"])))
    monkeypatch.setattr(sys, "argv", ["x", "--file", str(env), "--module", "lru_memory.batch", "--", "--backend", "chat", "--capacity", "3"])
    credentials.main()
    assert seen == [("lru_memory.batch", ["lru_memory.batch", "--backend", "chat", "--capacity", "3"], "fake-test-key")]
    monkeypatch.setattr(sys, "argv", ["x", "--file", str(env), "--module", "controller.batch"])
    with pytest.raises(SystemExit):
        credentials.main()


def test_report_labels_three_arms(tmp_path):
    runs = tmp_path / "runs"
    for arm in ("stateless", "memory", "memory_lru"):
        root = runs / arm
        initialize_arm(root, config(["faster", "noop", "faster"]), "mock", arm, 3, 1 if arm == "memory_lru" else None,
                       synthetic=True, pair_id="0")
        backend = RecordingLruBackend() if arm == "memory_lru" else LruMockBackend()
        engine_for(root, backend, SyntheticEvaluator()).run()
    result = report(runs, tmp_path / "report", make_figures=False)
    assert result["run_count"] == 3 and len(result["cohorts"]) == 1
    summary = read_json(tmp_path / "report" / result["cohorts"][0] / "summary.json")
    assert {r["condition"] for r in summary["analysis"]["runs"]} == {"stateless", "memory", "memory_lru"}
    assert summary["lru_capacity"] == 1
    assert summary["replicate_comparisons"][0]["memory_over_memory_lru_speedup"] == 1
    assert summary["lru_usage"][0]["evictions"] == 2
