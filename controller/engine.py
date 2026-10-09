from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time
import uuid

from agents.inputs import ContextLimit, PROMPTS, build_input, check_context, prompt_text
from agents.schemas import RoleResult
from benchmarks.metrics import write_json
from benchmarks.run import content_hash, environment
from benchmarks.runtime import PROJECT_ROOT
from controller.config import ExperimentConfig
from controller.evaluation import InfrastructureError
from controller.journal import Journal, RecoveryRequired, invoke_role
from controller.records import Attempt, Decision, MemoryEntry
from controller.storage import (app_hash, apply_edits, load_baseline, load_snapshot, patch_diff,
                                read_json, run_lock, save_snapshot)


def implementation_hashes() -> dict:
    paths = [PROJECT_ROOT / "requirements.lock", PROJECT_ROOT / "tests" / "test_notes.py"]
    for package in ("controller", "agents", "benchmarks"):
        paths.extend(p for p in (PROJECT_ROOT / package).rglob("*") if p.is_file() and p.suffix in {".py", ".txt", ".json"} and "__pycache__" not in p.parts)
    return {str(p.relative_to(PROJECT_ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def score(measurement: dict | None) -> float | None:
    if not measurement or measurement.get("complete") is False or not measurement.get("aggregate", {}).get("valid"):
        return None
    value = measurement["aggregate"].get("score_ms")
    return value if type(value) in (int, float) and math.isfinite(value) and value > 0 else None


def decide(validation: dict | None, parent: dict | None, candidate: dict | None, epsilon: float, status: str) -> Decision:
    if status != "evaluated":
        return Decision(accepted=False, reason=status)
    if not validation or not validation.get("correct"):
        return Decision(accepted=False, reason="correctness_not_passed")
    before, after = score(parent), score(candidate)
    if before is None or after is None:
        return Decision(accepted=False, reason="invalid_measurement")
    improvement = (before - after) / before
    accepted = improvement > epsilon
    return Decision(accepted=accepted, reason="improved_beyond_epsilon" if accepted else "insufficient_improvement", relative_improvement=improvement)


def initialize_run(root: Path, config: ExperimentConfig, backend_name: str, condition: str,
                   iterations: int, *, synthetic: bool = False, pair_id: str | None = None,
                   preflight: dict | None = None) -> dict:
    if condition not in {"memory", "stateless"} or backend_name not in {"mock", "codex"}:
        raise ValueError("Unknown condition or backend")
    if iterations < 1 or iterations > 30:
        raise ValueError("iterations must be between 1 and 30")
    if config.phase == "final" and (iterations != 30 or backend_name != "codex" or synthetic):
        raise ValueError("Final runs require 30 iterations and a real Codex backend")
    if config.phase == "final":
        from controller.freeze import validate_frozen
        validate_frozen(config)
    if config.phase == "pilot" and iterations > 10:
        raise ValueError("Pilot horizon is at most 10")
    if root.resolve().is_relative_to(PROJECT_ROOT):
        raise ValueError("Run artifacts must live outside the development repository")
    if (root / "manifest.json").exists():
        raise ValueError("Run already exists; use controller.resume")
    baseline_path = Path(config.baseline)
    if not baseline_path.is_absolute():
        baseline_path = PROJECT_ROOT / baseline_path
    files = load_baseline(baseline_path)
    digest = save_snapshot(root, files)
    settings = config.model_dump()
    protocol = {**settings, "benchmark": {k: v for k, v in settings["benchmark"].items() if k != "seed"}}
    implementation = implementation_hashes()
    runner_source = {name: (PROJECT_ROOT / name).read_text() for name in implementation}
    if any(hashlib.sha256(text.encode()).hexdigest() != implementation[name] for name, text in runner_source.items()):
        raise ValueError("Runner source changed while creating the reproducibility archive")
    write_json(root / "runner-source.json", {"schema_version": 1, "files": runner_source})
    manifest = {"schema_version": 1, "run_id": uuid.uuid4().hex, "created_at": time.time(),
                "backend": backend_name, "condition": condition, "iterations": iterations,
                "phase": config.phase, "synthetic": synthetic, "pair_id": pair_id,
                "config": settings, "config_hash": content_hash(settings),
                "protocol_hash": content_hash({"settings": protocol, "iterations": iterations, "baseline": digest}),
                "baseline_hash": digest, "baseline_files_hash": content_hash(files),
                "implementation": implementation, "runner_source_hash": content_hash(runner_source), "environment": environment(),
                "preflight": preflight,
                "prompts": {role: (PROMPTS / f"{role}.txt").read_text() for role in ("planner", "developer", "auditor")}}
    write_json(root / "manifest.json", manifest)
    return manifest


class Engine:
    def __init__(self, root: Path, backend, evaluator, crash_hook=None):
        self.root = root.resolve()
        self.manifest = read_json(self.root / "manifest.json")
        self.config = ExperimentConfig.model_validate(self.manifest["config"])
        self.backend = backend
        self.evaluator = evaluator
        self.journal = Journal(self.root)
        self.crash_hook = crash_hook or (lambda event: None)

    def verify(self):
        manifest = self.manifest
        if content_hash(manifest["config"]) != manifest["config_hash"]:
            raise ValueError("Frozen configuration hash mismatch")
        if manifest["implementation"] != implementation_hashes():
            raise ValueError("Runner/prompts/tests changed since run creation; resume requires the recorded implementation")
        archived_source = read_json(self.root / "runner-source.json")["files"]
        if content_hash(archived_source) != manifest["runner_source_hash"]:
            raise ValueError("Archived runner source changed")
        if manifest["environment"] != environment():
            raise ValueError("Runtime/dependencies changed since run creation")
        if bool(getattr(self.evaluator, "synthetic", False)) != manifest["synthetic"]:
            raise ValueError("Cannot mix synthetic and real evaluation")
        if manifest["backend"] == "codex" and not getattr(self.evaluator, "isolated", False):
            raise ValueError("Live candidates require container-isolated evaluation")
        baseline = load_snapshot(self.root, manifest["baseline_hash"])
        if content_hash(baseline) != manifest["baseline_files_hash"]:
            raise ValueError("Baseline contract/source changed")

    def attempts(self) -> list[dict]:
        records = []
        parent = self.manifest["baseline_hash"]
        contract = {k: v for k, v in load_snapshot(self.root, parent).items() if k.startswith("contracts/")}
        for index, path in enumerate(sorted((self.root / "attempts").glob("*.json")), 1):
            attempt = Attempt.model_validate(read_json(path)).model_dump()
            if attempt["iteration"] != index or attempt["parent_hash"] != parent or attempt["config_hash"] != self.manifest["config_hash"]:
                raise ValueError("Attempt sequence, parent, or configuration mismatch")
            retained = load_snapshot(self.root, attempt["retained_hash"])
            if {k: v for k, v in retained.items() if k.startswith("contracts/")} != contract:
                raise ValueError("Protected contract changed in snapshot")
            if attempt["retained_hash"] != (attempt["candidate_hash"] if attempt["decision"]["accepted"] else parent):
                raise ValueError("Acceptance/snapshot mismatch")
            parent = attempt["retained_hash"]
            records.append(attempt)
        return records

    def ask(self, iteration: int, role: str, payload: dict, files: dict, case: str) -> dict:
        key = f"{iteration:03d}-{role}"
        def action(artifacts):
            try:
                size = check_context(role, payload, files, self.config)
            except ContextLimit as error:
                write_json(artifacts / "input.json", payload)
                return RoleResult(status="context_limit", error=str(error)).model_dump()
            write_json(artifacts / "input-manifest.json", {"input_bytes_with_source": size,
                        "memory_count": payload["memory_count"], "memory_hash": payload["memory_hash"],
                        "prompt_hash": content_hash(prompt_text(role, payload)), "source_hash": app_hash(files)})
            return invoke_role(self.backend, role, payload, files, artifacts, case, self.config)
        return self.journal.step(key, action, paid=True)

    def evaluation(self, key: str, operation: str, files: dict, required: bool = False):
        def action(directory):
            result = getattr(self.evaluator, operation)(files, directory)
            if operation == "profile" and not result.get("valid"):
                raise InfrastructureError("Accepted parent profile failed; evidence retained for retry")
            if required and ((operation == "measure" and score(result) is None)
                             or (operation == "validate" and not result.get("correct"))):
                raise InfrastructureError(f"Required {operation} of accepted source failed; evidence retained for retry")
            return result
        return self.journal.step(key, action)

    def run_iteration(self, index: int, parent_hash: str, prior: list[dict]) -> dict:
        self.verify()
        parent = load_snapshot(self.root, parent_hash)
        profile = self.evaluation(f"{index:03d}-profile", "profile", parent)
        if not profile.get("valid"):
            raise InfrastructureError("Accepted parent could not be profiled; resolve infrastructure before resuming")
        case = self.config.mock_cases[(index - 1) % len(self.config.mock_cases)]
        history = [a["memory"] for a in prior] if self.manifest["condition"] == "memory" else None
        roles = {}
        payload = build_input("planner", evidence={"profile": profile["text"]}, memory=history)
        roles["planner"] = self.ask(index, "planner", payload, parent, case)
        plan = roles["planner"]["output"] if roles["planner"]["status"] == "ok" else None
        patch, validation, candidate_hash = [], None, None
        parent_measurement, candidate_measurement = None, None
        candidate = None
        status = "planner_" + roles["planner"]["status"]
        if plan:
            roles["developer"] = self.ask(index, "developer", build_input("developer", evidence={}, plan=plan), parent, case)
            status = "developer_" + roles["developer"]["status"]
            if roles["developer"]["status"] == "ok":
                patch = roles["developer"]["output"]["edits"]
                try:
                    candidate = apply_edits(parent, patch, self.config.max_output_bytes)
                    candidate_hash = save_snapshot(self.root, candidate)
                    patch_dir = self.root / "patches"
                    patch_dir.mkdir(exist_ok=True)
                    (patch_dir / f"{index:03d}.diff").write_text(patch_diff(parent, candidate))
                    status = "noop" if candidate_hash == parent_hash else "candidate"
                except ValueError as error:
                    status = "patch_rejected"
                    validation = {"correct": False, "status": status, "detail": str(error)}
                if status == "noop":
                    validation = {"correct": True, "status": "unchanged_validated_parent"}
                elif status == "candidate":
                    validation = self.evaluation(f"{index:03d}-validation", "validate", candidate)
                    status = validation["status"]
                    if validation.get("correct"):
                        # Alternate complete parent/candidate batches across iterations.
                        order = ("parent", "candidate") if index % 2 else ("candidate", "parent")
                        measurements = {}
                        for label in order:
                            files = parent if label == "parent" else candidate
                            measurements[label] = self.evaluation(f"{index:03d}-measure-{label}", "measure", files, required=label == "parent")
                        parent_measurement, candidate_measurement = measurements["parent"], measurements["candidate"]
                        if score(parent_measurement) is None:
                            raise InfrastructureError("Accepted parent measurement failed; do not count infrastructure as an optimization attempt")
                        status = "evaluated"
        decision = decide(validation, parent_measurement, candidate_measurement, self.config.epsilon, status)
        self.crash_hook("after_decision")
        # Raw measurement paths/timings are runner-owned; agents receive current summaries only.
        public_validation = {k: validation[k] for k in ("correct", "status") if k in validation} if validation else None
        evidence = {"validation": public_validation,
                    "parent": parent_measurement.get("aggregate") if parent_measurement else None,
                    "candidate": candidate_measurement.get("aggregate") if candidate_measurement else None}
        roles["auditor"] = self.ask(index, "auditor", build_input("auditor", evidence=evidence,
                                          plan=plan, patch=patch, decision=decision.model_dump()), candidate or parent, case)
        audit_status = "passed" if roles["auditor"]["status"] == "ok" else "failed"
        audit = roles["auditor"]["output"] if audit_status == "passed" else None
        retained = candidate_hash if decision.accepted else parent_hash
        baseline = self.journal.step("baseline-measure", lambda _: None)
        retained_score = score(candidate_measurement) if decision.accepted else (score(parent_measurement) or (prior[-1]["retained_score_ms"] if prior else score(baseline)))
        memory = MemoryEntry(iteration=index, parent_hash=parent_hash, candidate_hash=candidate_hash,
            hypothesis=plan["hypothesis"] if plan else None, attempted_change=plan["change"] if plan else None,
            approach=plan["approach"] if plan else None,
            facts={"status": status, "correctness": public_validation, "before_score_ms": score(parent_measurement),
                   "after_score_ms": score(candidate_measurement), "acceptance": decision.model_dump(),
                   "candidate_counts": candidate_measurement.get("aggregate", {}).get("counts") if candidate_measurement else None},
            interpretation=audit["interpretation"] if audit else None,
            limitations=audit["limitations"] if audit else ["Auditor unavailable; no explanation inferred."], audit_status=audit_status)
        attempt = Attempt(attempt_id=f"{self.manifest['run_id']}:{index:03d}", run_id=self.manifest["run_id"],
            iteration=index, condition=self.manifest["condition"], config_hash=self.manifest["config_hash"],
            parent_hash=parent_hash, candidate_hash=candidate_hash, retained_hash=retained, status=status,
            plan=plan, patch=patch, validation=validation, parent_measurement=parent_measurement,
            candidate_measurement=candidate_measurement, retained_score_ms=retained_score, decision=decision,
            audit=audit, audit_status=audit_status, roles=roles, memory=memory,
            synthetic=self.manifest["synthetic"]).model_dump()
        self.crash_hook("before_attempt_commit")
        self.verify()
        write_json(self.root / "attempts" / f"{index:03d}.json", attempt)
        self.crash_hook("after_attempt_commit")
        return attempt

    def materialize(self, attempts: list[dict]):
        # Records are authoritative; regenerate rather than append to two stores.
        write_json(self.root / "memory.json", {"schema_version": 1, "entries": [a["memory"] for a in attempts],
                                              "count": len(attempts), "hash": content_hash([a["memory"] for a in attempts])})
        self.crash_hook("after_memory_commit")
        for attempt in attempts:
            index = attempt["iteration"]
            if index in self.config.checkpoints:
                measurement = self.evaluation(f"{index:03d}-checkpoint", "measure", load_snapshot(self.root, attempt["retained_hash"]))
                write_json(self.root / "checkpoints" / f"{index:03d}.json", {"iteration": index,
                            "source_hash": attempt["retained_hash"], "measurement": measurement})

    def run(self) -> dict:
        with run_lock(self.root):
            self.verify()
            try:
                baseline = load_snapshot(self.root, self.manifest["baseline_hash"])
                validated = self.evaluation("baseline-validation", "validate", baseline, required=True)
                if not validated.get("correct"):
                    raise InfrastructureError("Frozen baseline did not pass the official suite")
                measured = self.evaluation("baseline-measure", "measure", baseline, required=True)
                if score(measured) is None:
                    raise InfrastructureError("Frozen baseline measurement is invalid")
                attempts = self.attempts()
                self.materialize(attempts)
                if any(role["status"] == "context_limit" for a in attempts for role in a["roles"].values()):
                    state = {"status": "context_limit", "completed_iterations": len(attempts), "reason": "Recorded full-history context limit; no automatic continuation"}
                    write_json(self.root / "state.json", state)
                    return state
                for index in range(len(attempts) + 1, self.manifest["iterations"] + 1):
                    parent_hash = attempts[-1]["retained_hash"] if attempts else self.manifest["baseline_hash"]
                    attempt = self.run_iteration(index, parent_hash, attempts)
                    attempts.append(attempt)
                    self.materialize(attempts)
                    if any(role["status"] == "context_limit" for role in attempt["roles"].values()):
                        state = {"status": "context_limit", "completed_iterations": len(attempts), "reason": "Full-history protocol cannot continue within context budget"}
                        write_json(self.root / "state.json", state)
                        return state
                final = self.evaluation("final-remeasurement", "measure", load_snapshot(self.root, attempts[-1]["retained_hash"]), required=True)
                state = {"status": "complete", "completed_iterations": len(attempts), "retained_hash": attempts[-1]["retained_hash"],
                         "final_remeasurement_score_ms": score(final)}
                write_json(self.root / "state.json", state)
                return state
            except (InfrastructureError, RecoveryRequired) as error:
                state = {"status": "needs_attention", "completed_iterations": len(self.attempts()), "reason": str(error)}
                write_json(self.root / "state.json", state)
                raise
