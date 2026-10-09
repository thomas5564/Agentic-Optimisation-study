from __future__ import annotations

from pathlib import Path
import time
import uuid

from agents.process import redact
from agents.schemas import OUTPUTS, RoleResult
from benchmarks.metrics import write_json
from benchmarks.run import content_hash
from controller.storage import read_json


class RecoveryRequired(RuntimeError):
    pass


class Journal:
    def __init__(self, root: Path):
        self.root = root

    def step(self, key: str, action, paid: bool = False):
        path = self.root / "journal" / f"{key}.json"
        if path.exists():
            previous = read_json(path)
            if previous["status"] == "complete":
                if previous.get("result_hash") != content_hash(previous["result"]):
                    raise ValueError(f"Journal result hash mismatch: {key}")
                return previous["result"]
            if paid:
                raise RecoveryRequired(f"Call {key} has an unknown outcome. Inspect its artifacts and use resume --abandon-call {key} if it cannot be recovered. It will not be called again automatically.")
        attempt = uuid.uuid4().hex
        write_json(path, {"status": "started", "paid": paid, "execution_id": attempt, "started_at": time.time()})
        artifacts = self.root / "artifacts" / key / attempt
        artifacts.mkdir(parents=True, exist_ok=True)
        result = action(artifacts)
        write_json(path, {"status": "complete", "paid": paid, "execution_id": attempt, "result": result, "result_hash": content_hash(result)})
        return result

    def abandon_call(self, key: str):
        if "/" in key or ".." in key:
            raise ValueError("Invalid call key")
        path = self.root / "journal" / f"{key}.json"
        state = read_json(path)
        if state["status"] != "started" or not state["paid"]:
            raise ValueError("Only an unresolved role call may be abandoned")
        state.update(status="complete", result=RoleResult(status="interrupted_unknown", error="Operator marked unresolved call failed; it was not repeated").model_dump())
        state["result_hash"] = content_hash(state["result"])
        state["resolution"] = "explicit_abandon"
        write_json(path, state)


    def recover_call(self, key: str):
        if "/" in key or ".." in key:
            raise ValueError("Invalid call key")
        path = self.root / "journal" / f"{key}.json"
        state = read_json(path)
        if state["status"] != "started" or not state["paid"]:
            raise ValueError("Only an unresolved role call may be recovered")
        role = key.split("-", 1)[1]
        result_path = self.root / "artifacts" / key / state["execution_id"] / "result.json"
        result = RoleResult.model_validate(read_json(result_path))
        if result.status == "ok":
            OUTPUTS[role].model_validate(result.output)
        state.update(status="complete", result=result.model_dump(), resolution="explicit_saved_result_recovery")
        state["result_hash"] = content_hash(state["result"])
        write_json(path, state)


def invoke_role(backend, role, payload, files, artifacts, case, config):
    from controller.storage import workspace
    started = time.monotonic()
    write_json(artifacts / "input.json", payload)
    with workspace(files) as root:
        try:
            result = backend.invoke(role, payload, root, artifacts, case)
        except TimeoutError:
            result = RoleResult(status="timeout", error="Role timed out")
    if result.elapsed_seconds is None:
        result.elapsed_seconds = time.monotonic() - started
    # Sanitize model output before it can enter patches, memory, or researcher logs.
    result = RoleResult.model_validate_json(redact(result.model_dump_json()))
    if result.status == "ok":
        try:
            parsed = OUTPUTS[role].model_validate(result.output)
            if len(parsed.model_dump_json().encode()) > config.max_output_bytes:
                raise ValueError("Structured output exceeds configured size budget")
            result.output = parsed.model_dump()
        except ValueError as error:
            result.status = "malformed"
            result.error = str(error)
    write_json(artifacts / "result.json", result.model_dump())
    return result.model_dump()
