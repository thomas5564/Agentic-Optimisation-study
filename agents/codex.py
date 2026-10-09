from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import uuid

from agents.docker import PrerequisiteError, container_command, inspect_image, mount, remove_container
from agents.process import redact, run_process
from agents.schemas import OUTPUTS, RoleResult
from benchmarks.metrics import write_json

REQUIRED_FLAGS = ("--ephemeral", "--ignore-user-config", "--ignore-rules", "--output-schema",
                  "--output-last-message", "--json", "--skip-git-repo-check", "--sandbox")


def codex_arguments(config) -> list[str]:
    return ["codex", "--no-daemon", "--ask-for-approval", "never", "exec",
            "--model", config.model, "--sandbox", "read-only", "--ephemeral",
            "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check",
            "--json", "--color", "never", "--cd", "/workspace",
            "-c", f"model_reasoning_effort={json.dumps(config.reasoning)}",
            "--output-schema", "/input/schema.json", "--output-last-message", "/result/answer.json", "-"]


def inspect_cli(config) -> dict:
    evidence = inspect_image(config.image)
    for label, args in (("version", ["--version"]), ("help", ["exec", "--help"]), ("global_help", ["--help"])):
        name = "notes-preflight-" + uuid.uuid4().hex
        command = container_command(config.image, name) + ["--workdir", "/tmp", config.image, "codex", *args]
        try:
            result = run_process(command, timeout=20)
        finally:
            remove_container(name)
        if result.returncode or result.failure:
            raise PrerequisiteError("Codex CLI is unavailable in the configured image")
        evidence[label] = result.stdout
    if not all(flag in evidence["help"] for flag in REQUIRED_FLAGS) or "--no-daemon" not in evidence["global_help"]:
        raise PrerequisiteError("Container Codex CLI lacks required fresh-session/structured-output flags")
    return evidence


class CodexBackend:
    def __init__(self, config):
        self.config = config

    def preflight(self):
        if not self.config.model:
            raise PrerequisiteError("Set an explicit model in the experiment config")
        if not os.environ.get("CODEX_API_KEY"):
            raise PrerequisiteError("Set CODEX_API_KEY outside source control; host login/home is never mounted")
        from agents.preflight import isolation_probe
        evidence = inspect_cli(self.config)
        evidence["isolation_probe"] = isolation_probe(self.config)
        return evidence

    def invoke(self, role: str, payload: dict, workspace: Path, artifacts: Path, case: str = "noop") -> RoleResult:
        from agents.inputs import prompt_text
        config = self.config
        artifacts.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="notes-role-io-") as directory:
            io = Path(directory)
            incoming, outgoing = io / "input", io / "result"
            incoming.mkdir()
            outgoing.mkdir()
            write_json(incoming / "schema.json", OUTPUTS[role].model_json_schema())
            name = "notes-role-" + uuid.uuid4().hex
            command = container_command(config.image, name, config.agent_network)
            command += mount(workspace, "/workspace") + mount(incoming, "/input") + mount(outgoing, "/result", False)
            command += ["--env", "CODEX_API_KEY", config.image, *codex_arguments(config)]
            try:
                result = run_process(command, stdin=prompt_text(role, payload), timeout=config.role_timeout_seconds,
                                     max_bytes=config.max_output_bytes * 8, max_tool_calls=config.max_tool_calls)
            finally:
                remove_container(name)
            (artifacts / "events.jsonl").write_text(result.stdout)
            (artifacts / "stderr.txt").write_text(result.stderr)
            write_json(artifacts / "command.json", {"command": command, "credentials": "environment only; redacted"})
            usage = None
            compacted = False
            for line in result.stdout.splitlines():
                try:
                    event = json.loads(line)
                    if event.get("type") == "turn.completed":
                        usage = event.get("usage") if isinstance(event.get("usage"), dict) else None
                    if any("compact" in str(x).lower() for x in (event.get("type", ""), event.get("item", {}).get("type", ""), event.get("payload", {}).get("type", ""))):
                        compacted = True
                except (ValueError, AttributeError):
                    pass
            metadata = {"model": config.model, "reasoning": config.reasoning, "image": config.image}
            common = dict(elapsed_seconds=float(result.elapsed), exit_code=result.returncode, usage=usage, metadata=metadata)
            if compacted or "context window" in result.stderr.lower() or "context_length_exceeded" in result.stdout:
                return RoleResult(status="context_limit", error="Context overflow/compaction detected; full-history protocol stopped", **common)
            if result.failure:
                return RoleResult(status="timeout" if result.failure == "timeout" else "agent_error", error=result.failure, **common)
            if result.returncode == 125:
                raise PrerequisiteError("Docker failed to launch the role container; inspect redacted stderr")
            if result.returncode:
                return RoleResult(status="agent_error", error="Codex exited unsuccessfully; see redacted transcript", **common)
            answer = outgoing / "answer.json"
            if not answer.is_file() or answer.is_symlink() or answer.stat().st_size > config.max_output_bytes:
                return RoleResult(status="malformed", error="Missing or oversized structured answer", **common)
            text = redact(answer.read_text())
            (artifacts / "answer.json").write_text(text)
            try:
                output = json.loads(text)
                if not isinstance(output, dict):
                    raise ValueError("Expected object")
            except ValueError:
                return RoleResult(status="malformed", error="Invalid JSON answer", **common)
            return RoleResult(status="ok", output=output, **common)
