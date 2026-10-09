from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

from agents.docker import container_command, mount, remove_container
from agents.process import run_process
from benchmarks.metrics import write_json
from benchmarks.runtime import PROJECT_ROOT, benchmark_lock
from controller.storage import read_json, workspace


class InfrastructureError(RuntimeError):
    pass


class Evaluator:
    synthetic = False

    def __init__(self, config, isolated: bool = False):
        self.config = config
        self.isolated = isolated

    def execute(self, operation: str, files: dict, output: Path) -> dict:
        output.mkdir(parents=True, exist_ok=True)
        with workspace(files) as root, tempfile.TemporaryDirectory(prefix="notes-eval-input-") as temp:
            inputs = Path(temp)
            write_json(inputs / "benchmark.json", self.config.benchmark)
            (root / "tests").mkdir()
            shutil.copyfile(PROJECT_ROOT / "tests" / "test_notes.py", root / "tests" / "test_notes.py")
            name = "notes-eval-" + uuid.uuid4().hex
            if self.isolated:
                command = container_command(self.config.image, name)
                command += mount(root, "/workspace") + mount(inputs, "/input") + mount(output, "/result", False)
                # Expose only evaluator modules and dependencies; never researcher artifacts.
                for package in ("controller", "benchmarks", "agents"):
                    command += mount(PROJECT_ROOT / package, f"/runner/{package}")
                command += ["--env", "PYTHONPATH=/runner", self.config.image, "python", "-m", "controller.worker",
                            "--operation", operation, "--root", "/workspace", "--output", "/result", "--config", "/input/benchmark.json"]
                env = None
            else:
                # This mode is for controlled mock patches only, never live model output.
                command = [sys.executable, "-m", "controller.worker", "--operation", operation,
                           "--root", str(root), "--output", str(output.resolve()), "--config", str(inputs / "benchmark.json")]
                env = {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "LC_ALL", "TMPDIR"}}
                env.update({"PYTHONPATH": str(PROJECT_ROOT), "HOME": temp, "PYTHONDONTWRITEBYTECODE": "1",
                            "NOTES_DB_PATH": str(inputs / "notes.db"), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
            try:
                with benchmark_lock():
                    process = run_process(command, cwd=inputs, env=env, timeout=self.config.evaluation_timeout_seconds)
            finally:
                if self.isolated:
                    remove_container(name)
            (output / "stdout.txt").write_text(process.stdout)
            (output / "stderr.txt").write_text(process.stderr)
            if process.failure == "timeout":
                if operation == "validate":
                    return {"correct": False, "status": "validation_timeout", "detail": "Evaluation timeout"}
                if operation == "measure":
                    partial = read_json(output / "result.json") if (output / "result.json").exists() else {"runs": []}
                    partial.update(complete=False, error="measurement_timeout", artifacts=str(output), synthetic=False)
                    partial["aggregate"] = {**partial.get("aggregate", {}), "valid": False, "score_ms": None}
                    write_json(output / "result.json", partial)
                    return partial
                raise InfrastructureError(f"{operation} exceeded evaluation budget; raw evidence retained in {output}")
            if process.returncode or process.failure or not (output / "result.json").exists():
                raise InfrastructureError(f"{operation} worker failed; see {output}")
            result = read_json(output / "result.json")
            if result.get("status") == "infrastructure_error":
                raise InfrastructureError(f"Official tests could not complete; see {output}")
            result["artifacts"] = str(output)
            return result

    def validate(self, files: dict, output: Path) -> dict:
        return self.execute("validate", files, output)

    def measure(self, files: dict, output: Path) -> dict:
        return self.execute("measure", files, output)

    def profile(self, files: dict, output: Path) -> dict:
        return self.execute("profile", files, output)
