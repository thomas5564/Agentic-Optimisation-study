from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import httpx

from benchmarks.config import BenchmarkConfig

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def benchmark_lock():
    path = Path(tempfile.gettempdir()) / f"notes-benchmark-{os.getuid()}.lock"
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another benchmark/profile is running; measurements must be serial") from error
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def candidate_server(app_root: Path, config: BenchmarkConfig, log_path: Path, profile: Path | None = None,
                     database: Path | None = None):
    if not (app_root / "app" / "main.py").is_file():
        raise ValueError(f"Candidate app/main.py is missing from {app_root}")
    with tempfile.TemporaryDirectory(prefix="notes-measure-") as directory:
        scratch = Path(directory)
        ready = scratch / "ready"
        active = scratch / "profile-active"
        command = [sys.executable, "-m", "benchmarks.server", "--app-root", str(app_root.resolve()), "--ready", str(ready)]
        if profile:
            command += ["--profile", str(profile.resolve()), "--profile-active", str(active)]
        env = {**os.environ, "NOTES_DB_PATH": str(database or scratch / "notes.db"),
               "PYTHONPATH": str(PROJECT_ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w") as log:
            process = subprocess.Popen(command, cwd=scratch, env=env, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + config.startup_timeout_seconds
                while not ready.exists():
                    if process.poll() is not None:
                        raise RuntimeError(f"Candidate import/startup failed; see {log_path}")
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"Candidate startup timed out; see {log_path}")
                    time.sleep(.02)
                with httpx.Client(base_url=f"http://127.0.0.1:{ready.read_text()}",
                                  timeout=config.timeout_seconds, trust_env=False) as client:
                    while True:
                        if process.poll() is not None:
                            raise RuntimeError(f"Candidate exited at startup; see {log_path}")
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError(f"Candidate startup timed out; see {log_path}")
                        try:
                            client.get("/notes", timeout=min(.2, remaining))
                            break
                        except httpx.TransportError:
                            time.sleep(.02)
                    yield client, active
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
