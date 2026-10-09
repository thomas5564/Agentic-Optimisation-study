"""Synthetic timings here are test fixtures, never experiment measurements."""
from copy import deepcopy
from pathlib import Path

import pytest

from agents.mock import MockBackend
from agents.schemas import RoleResult
from controller.config import ExperimentConfig
from controller.engine import Engine, decide, initialize_run
from controller.evaluation import InfrastructureError
from controller.journal import Journal, RecoveryRequired
from controller.storage import app_hash, apply_edits, load_snapshot, read_json


class SyntheticEvaluator:
    synthetic = True
    isolated = False

    def __init__(self, factor=.8):
        self.factor = factor
        self.calls = []

    def validate(self, files, output):
        self.calls.append(("validate", app_hash(files)))
        try:
            for path, text in files.items():
                if path.endswith(".py"):
                    compile(text, path, "exec")
        except SyntaxError:
            return {"correct": False, "status": "syntax_failed"}
        return {"correct": True, "status": "passed"}

    def profile(self, files, output):
        self.calls.append(("profile", app_hash(files)))
        return {"valid": True, "text": "SYNTHETIC TEST PROFILE", "synthetic": True}

    def measure(self, files, output):
        self.calls.append(("measure", app_hash(files)))
        changes = files['app/__init__.py'].count('Mock candidate fixture')
        score = 10 * self.factor ** changes
        return {"synthetic": True, "aggregate": {"valid": True, "score_ms": score,
                "counts": {"total": 10, "successful": 10, "failed": 0, "success_rate": 1.0}}, "runs": []}


class RecordingBackend(MockBackend):
    def __init__(self):
        self.calls = []

    def invoke(self, role, payload, workspace, artifacts, case="noop"):
        self.calls.append((role, deepcopy(payload)))
        assert set(p.name for p in workspace.iterdir()) == {"app", "contracts"}
        assert not (workspace / ".git").exists()
        return super().invoke(role, payload, workspace, artifacts, case)


def config(cases=None, **overrides):
    return ExperimentConfig(epsilon=.1, benchmark={"seed": 7, "note_count": 2, "cycles": 1, "repetitions": 1},
                            mock_cases=cases or ["faster"], **overrides)


def create(tmp_path, cases=None, condition="stateless", iterations=1, evaluator=None, backend=None, **overrides):
    cfg = config(cases, **overrides)
    initialize_run(tmp_path, cfg, "mock", condition, iterations, synthetic=True)
    return Engine(tmp_path, backend or RecordingBackend(), evaluator or SyntheticEvaluator())


def test_only_valid_improvement_beyond_epsilon_accepted():
    def measurement(value, valid=True):
        return {"aggregate": {"valid": valid, "score_ms": value}}
    valid = {"correct": True}
    assert decide(valid, measurement(10), measurement(8), .1, "evaluated").accepted
    assert not decide(valid, measurement(10), measurement(9), .1, "evaluated").accepted
    assert not decide(valid, measurement(10), measurement(11), .1, "evaluated").accepted
    assert not decide(valid, measurement(10), measurement(.1, False), .1, "evaluated").accepted
    assert not decide({"correct": False}, measurement(10), measurement(1), .1, "evaluated").accepted
    assert not decide(valid, measurement(0), measurement(1), .1, "evaluated").accepted


@pytest.mark.parametrize("case,factor,accepted,status", [
    ("faster", .8, True, "evaluated"), ("slower", 1.2, False, "evaluated"),
    ("broken", .8, False, "syntax_failed"), ("malformed", .8, False, "planner_malformed"),
    ("noop", .8, False, "noop"), ("timeout", .8, False, "planner_timeout"),
    ("forbidden", .8, False, "patch_rejected"), ("audit_failure", .8, True, "evaluated"),
])
def test_attempt_outcomes_and_exact_rollback(tmp_path, case, factor, accepted, status):
    engine = create(tmp_path, [case], evaluator=SyntheticEvaluator(factor))
    assert engine.run()["status"] == "complete"
    attempt = engine.attempts()[0]
    assert attempt["decision"]["accepted"] == accepted
    assert attempt["status"] == status
    if not accepted:
        assert attempt["retained_hash"] == engine.manifest["baseline_hash"]
    else:
        assert attempt["retained_hash"] == attempt["candidate_hash"] != attempt["parent_hash"]
    assert attempt["memory"]["facts"]["acceptance"] == attempt["decision"]
    assert attempt["roles"]["planner"]["usage"] is None
    if case == "audit_failure":
        assert attempt["audit_status"] == "failed"
        assert attempt["memory"]["interpretation"] is None
    assert read_json(tmp_path / "memory.json")["count"] == 1


@pytest.mark.parametrize("condition", ["stateless", "memory"])
def test_three_iterations_memory_boundaries_and_retention(tmp_path, condition):
    engine = create(tmp_path, ["faster", "broken", "noop"], condition, 3)
    assert engine.run()["status"] == "complete"
    planners = [p for role, p in engine.backend.calls if role == "planner"]
    assert [p["memory_count"] for p in planners] == ([0, 1, 2] if condition == "memory" else [0, 0, 0])
    for role, payload in engine.backend.calls:
        if role != "planner" or condition == "stateless":
            assert payload["memory"] is None
    attempts = engine.attempts()
    assert attempts[1]["parent_hash"] == attempts[0]["candidate_hash"]
    assert attempts[2]["parent_hash"] == attempts[1]["retained_hash"]
    assert read_json(tmp_path / "memory.json")["entries"] == [a["memory"] for a in attempts]
    if condition == "memory":
        assert planners[2]["memory"] == [a["memory"] for a in attempts[:2]]


@pytest.mark.parametrize("point", ["after_decision", "before_attempt_commit", "after_attempt_commit", "after_memory_commit"])
def test_resume_around_acceptance_and_memory_does_not_duplicate_calls(tmp_path, point):
    engine = create(tmp_path)
    fired = False
    def crash(event):
        nonlocal fired
        if event == point and not fired:
            if point == "after_memory_commit" and not (tmp_path / "attempts" / "001.json").exists():
                return
            fired = True
            raise KeyboardInterrupt("forced interruption")
    engine.crash_hook = crash
    with pytest.raises(KeyboardInterrupt):
        engine.run()
    resumed = Engine(tmp_path, engine.backend, engine.evaluator)
    assert resumed.run()["status"] == "complete"
    assert len(resumed.attempts()) == 1
    assert [role for role, _ in engine.backend.calls] == ["planner", "developer", "auditor"]
    assert read_json(tmp_path / "memory.json")["count"] == 1
    calls = list(engine.backend.calls)
    assert resumed.run()["status"] == "complete"
    assert engine.backend.calls == calls


def test_unknown_paid_outcome_requires_explicit_recovery(tmp_path):
    class InterruptedBackend(RecordingBackend):
        def invoke(self, role, payload, workspace, artifacts, case="noop"):
            if role == "developer":
                self.calls.append((role, deepcopy(payload)))
                raise KeyboardInterrupt("lost outcome")
            return super().invoke(role, payload, workspace, artifacts, case)
    engine = create(tmp_path, backend=InterruptedBackend())
    with pytest.raises(KeyboardInterrupt):
        engine.run()
    with pytest.raises(RecoveryRequired):
        Engine(tmp_path, engine.backend, engine.evaluator).run()
    assert [r for r, _ in engine.backend.calls] == ["planner", "developer"]
    Journal(tmp_path).abandon_call("001-developer")
    resumed = Engine(tmp_path, engine.backend, engine.evaluator)
    assert resumed.run()["status"] == "complete"
    assert resumed.attempts()[0]["status"] == "developer_interrupted_unknown"
    assert [r for r, _ in engine.backend.calls].count("developer") == 1


def test_context_limit_stops_without_truncation_or_automatic_continuation(tmp_path):
    engine = create(tmp_path, condition="memory", iterations=3, max_input_bytes=10)
    assert engine.run()["status"] == "context_limit"
    assert engine.backend.calls == []
    assert len(engine.attempts()) == 1
    assert Engine(tmp_path, engine.backend, engine.evaluator).run()["status"] == "context_limit"
    assert len(engine.attempts()) == 1


def test_auditor_cannot_override_runner_facts(tmp_path):
    class HostileAuditor(RecordingBackend):
        def invoke(self, role, payload, workspace, artifacts, case="noop"):
            result = super().invoke(role, payload, workspace, artifacts, case)
            if role == "auditor":
                result.output["accepted"] = True
                result.output["score_ms"] = .0001
            return result
    engine = create(tmp_path, ["slower"], evaluator=SyntheticEvaluator(2), backend=HostileAuditor())
    engine.run()
    attempt = engine.attempts()[0]
    assert not attempt["decision"]["accepted"]
    assert attempt["audit_status"] == "failed"
    assert attempt["candidate_measurement"]["aggregate"]["score_ms"] == 20


@pytest.mark.parametrize("path", ["../tests/test_notes.py", "/tmp/x.py", "app/../../x.py", "app/.hidden.py", "app//db.py", "contracts/API.md", "app/sitecustomize.py", "app\\evil.py"])
def test_patch_allowlist_rejects_escapes_and_protected_files(path):
    with pytest.raises(ValueError):
        apply_edits({"app/main.py": "", "app/__init__.py": ""}, [{"path": path, "content": ""}], 10000)


def test_infrastructure_failure_retries_stage_without_counting_attempt(tmp_path):
    class FailingEvaluator(SyntheticEvaluator):
        fail = True
        def profile(self, files, output):
            if self.fail:
                self.fail = False
                raise InfrastructureError("fixture infrastructure error")
            return super().profile(files, output)
    engine = create(tmp_path, evaluator=FailingEvaluator())
    with pytest.raises(InfrastructureError):
        engine.run()
    assert engine.attempts() == []
    assert engine.run()["status"] == "complete"
    assert len(engine.attempts()) == 1


def test_configuration_drift_and_synthetic_mixing_rejected(tmp_path):
    engine = create(tmp_path)
    from benchmarks.metrics import write_json
    manifest = read_json(tmp_path / "manifest.json")
    manifest["config"]["epsilon"] = .9
    write_json(tmp_path / "manifest.json", manifest)
    with pytest.raises(ValueError, match="configuration hash"):
        Engine(tmp_path, engine.backend, engine.evaluator).run()


def test_final_requires_prerequisites_and_full_horizon():
    with pytest.raises(ValueError):
        config(phase="final")


def test_saved_role_result_recovery_never_reissues_call(tmp_path):
    from benchmarks.metrics import write_json
    journal = Journal(tmp_path)
    def call(artifacts):
        write_json(artifacts / "result.json", RoleResult(status="timeout", error="known timeout").model_dump())
        raise KeyboardInterrupt("crash after result capture")
    with pytest.raises(KeyboardInterrupt):
        journal.step("001-planner", call, paid=True)
    journal.recover_call("001-planner")
    result = journal.step("001-planner", lambda _: pytest.fail("must not call again"), paid=True)
    assert result["status"] == "timeout"


def test_parent_candidate_measurement_order_alternates(tmp_path):
    engine = create(tmp_path, ["faster"], iterations=2)
    engine.run()
    attempts = engine.attempts()
    measures = [digest for operation, digest in engine.evaluator.calls if operation == "measure"]
    # Baseline, then parent/candidate, then candidate/parent, then final remeasurement.
    assert measures == [engine.manifest["baseline_hash"], attempts[0]["parent_hash"], attempts[0]["candidate_hash"],
                        attempts[1]["candidate_hash"], attempts[1]["parent_hash"], attempts[1]["retained_hash"]]


def test_real_evaluator_runs_official_checks_against_separate_candidate_processes(tmp_path):
    from controller.evaluation import Evaluator
    from controller.storage import load_baseline
    from benchmarks.runtime import PROJECT_ROOT
    files = load_baseline(PROJECT_ROOT / "research" / "baseline")
    files["app/db.py"] = files["app/db.py"].replace('title=row["title"],', 'title="incorrect candidate value",')
    evaluator = Evaluator(config())
    result = evaluator.validate(files, tmp_path / "validation")
    assert result["correct"] is False
    assert result["status"] == "correctness_failed"
    output = (tmp_path / "validation" / "tests.txt").read_text()
    assert "incorrect candidate value" in output


def test_baseline_and_runner_are_archived_without_researcher_history(tmp_path):
    engine = create(tmp_path)
    archived = read_json(tmp_path / "runner-source.json")["files"]
    assert "controller/engine.py" in archived and "tests/test_notes.py" in archived
    assert not any(name.startswith(("docs/", "research/", ".git/")) for name in archived)
    from benchmarks.run import content_hash
    assert content_hash(archived) == engine.manifest["runner_source_hash"]


def test_explicit_disabled_sqlite_durability_is_rejected():
    with pytest.raises(ValueError, match="durability"):
        apply_edits({"app/main.py":"", "app/__init__.py":""},
                    [{"path":"app/main.py", "content":'connection.execute("PRAGMA synchronous = OFF")'}],10000)
