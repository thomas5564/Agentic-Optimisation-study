import json
from pathlib import Path
import sys

import pytest

from agents.codex import CodexBackend, codex_arguments
from agents.docker import PrerequisiteError, container_command, mount
from agents.process import ProcessResult, redact, run_process
from agents.schemas import Audit, OUTPUTS
from controller.config import ExperimentConfig
from controller.journal import invoke_role


def config():
    return ExperimentConfig(epsilon=.2, benchmark={"note_count":2}, model="explicit-test-model",
                            image="sha256:" + "1"*64)


def test_container_has_only_explicit_mounts_and_no_host_privileges(tmp_path):
    command = container_command(config().image, "test")
    assert command[:4] == ["docker", "run", "-i", "--rm"]
    assert "--read-only" in command and "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert command[command.index("--network")+1] == "none"
    assert not any(x in command for x in ("--privileged", "--pid=host", "--network=host"))
    assert mount(tmp_path, "/workspace")[1].endswith(",readonly")
    with pytest.raises(PrerequisiteError):
        container_command("latest", "test")
    with pytest.raises(PrerequisiteError):
        container_command(config().image, "test", "host")


def test_codex_command_has_fresh_session_flags_and_explicit_model():
    command = codex_arguments(config())
    for flag in ("--ephemeral", "--ignore-user-config", "--ignore-rules", "--no-daemon", "--output-schema", "--json"):
        assert flag in command
    assert command[command.index("--model") + 1] == "explicit-test-model"
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "resume" not in command and "fork" not in command


def test_missing_model_and_credentials_fail_without_call(monkeypatch):
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    with pytest.raises(PrerequisiteError, match="CODEX_API_KEY"):
        CodexBackend(config()).preflight()
    with pytest.raises(PrerequisiteError, match="explicit model"):
        CodexBackend(config().model_copy(update={"model":None})).preflight()


def test_subprocess_timeout_and_redaction(monkeypatch):
    monkeypatch.setenv("CODEX_API_KEY", "secret-value-for-test")
    result = run_process([sys.executable, "-c", "import time; print('secret-value-for-test', flush=True); time.sleep(5)"], timeout=.1)
    assert result.failure == "timeout"
    assert result.elapsed < 2
    assert "secret-value-for-test" not in result.stdout
    assert "[REDACTED]" in result.stdout
    assert redact("Authorization: Bearer abc.def.ghi") == "Authorization: Bearer [REDACTED]"


def test_subprocess_output_budget():
    result = run_process([sys.executable, "-c", "print('x'*10000)"], max_bytes=100)
    assert result.failure == "output_limit"
    assert len(result.stdout) <= 100


@pytest.mark.parametrize("mode,status", [("ok","ok"),("bad_json","malformed"),("exit","agent_error"),("timeout","timeout"),("compacted","context_limit")])
def test_codex_subprocess_outcomes_and_no_host_roots(monkeypatch, tmp_path, mode, status):
    import agents.codex as module
    calls = []
    def fake_run(command, **kwargs):
        calls.append(command)
        assert str(Path.home()) not in command
        mounts = [command[i+1] for i,c in enumerate(command) if c == "--mount"]
        assert len(mounts) == 3
        assert all(not any(s in m for s in ('docker.sock', '/.codex', '/.git')) for m in mounts)
        result_mount = next(m for m in mounts if 'dst=/result' in m)
        root = Path(result_mount.split('src=')[1].split(',')[0])
        if mode == "ok":
            (root / "answer.json").write_text(json.dumps({"schema_version":1,"interpretation":"test","limitations":[]}))
        if mode == "bad_json":
            (root / "answer.json").write_text("bad JSON")
        stdout = '{"type":"context_compacted"}\n' if mode == "compacted" else '{"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":3}}\n'
        return ProcessResult(1 if mode == "exit" else 0, stdout, "", .2, "timeout" if mode == "timeout" else None)
    monkeypatch.setattr(module,"run_process",fake_run)
    monkeypatch.setattr(module,"remove_container",lambda name:None)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = CodexBackend(config()).invoke("auditor", {}, workspace, tmp_path / "artifacts")
    assert result.status == status
    if mode == "ok":
        assert result.usage == {"input_tokens":12,"output_tokens":3}
    assert len(calls) == 1


def test_audit_schema_has_no_factual_override_fields():
    with pytest.raises(ValueError):
        Audit.model_validate({"schema_version":1,"interpretation":"OK","limitations":[],"accepted":True})


def test_committed_role_schemas_match_models():
    for role, model in OUTPUTS.items():
        path = Path(__file__).resolve().parents[1] / "agents" / "schemas" / f"{role}.json"
        assert json.loads(path.read_text()) == model.model_json_schema()


def test_redaction_preserves_nonsecret_cli_configuration_text():
    assert redact('disk-full-read-access --ask-for-approval bearer token') == 'disk-full-read-access --ask-for-approval bearer token'


def test_fast_exiting_process_cannot_evade_tool_budget():
    program = 'import json; print(json.dumps({"type":"item.completed","item":{"id":"one","type":"command_execution"}}))'
    result = run_process([sys.executable, "-c", program], max_tool_calls=0)
    assert result.failure == "tool_limit"
