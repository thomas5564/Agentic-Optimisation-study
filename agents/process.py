"""Bounded subprocess capture; no credentials in persisted transcripts."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time


def redact(text: str) -> str:
    for name in ("CODEX_API_KEY", "OPENAI_API_KEY"):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[REDACTED]")
    text = re.sub(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}", "[REDACTED]", text)
    text = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._-]+", r"\1[REDACTED]", text)
    return re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._-]{20,}", r"\1[REDACTED]", text)


@dataclass
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    elapsed: float
    failure: str | None = None


def kill_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        # macOS can report EPERM when a short-lived child exits between poll/kill.
        # Only suppress it if that child is demonstrably already gone.
        process.wait(timeout=.1)


def count_tool_calls(data: str) -> int:
    tool_ids = set()
    for line in data.splitlines():
        try:
            item = json.loads(line).get("item", {})
            if item.get("type") in {"command_execution", "file_change", "mcp_tool_call", "web_search"}:
                tool_ids.add(item.get("id", line))
        except (ValueError, AttributeError):
            pass
    return len(tool_ids)


def run_process(command: list[str], *, cwd: Path | None = None, env: dict | None = None,
                stdin: str = "", timeout: float = 120, max_bytes: int = 8000000,
                max_tool_calls: int | None = None) -> ProcessResult:
    started = time.monotonic()
    failure = None
    with tempfile.TemporaryFile() as input_file, tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        input_file.write(stdin.encode())
        input_file.seek(0)
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=input_file,
                                   stdout=out, stderr=err, start_new_session=True)
        try:
            while process.poll() is None:
                if time.monotonic() - started >= timeout:
                    failure = "timeout"
                elif os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > max_bytes:
                    failure = "output_limit"
                elif max_tool_calls is not None:
                    # Read without moving the child's shared file position.
                    data = os.pread(out.fileno(), min(os.fstat(out.fileno()).st_size, max_bytes), 0).decode(errors="replace")
                    if count_tool_calls(data) > max_tool_calls:
                        failure = "tool_limit"
                if failure:
                    kill_group(process)
                    break
                time.sleep(.02)
            process.wait()
        finally:
            # A subprocess may have launched children. Never leave them after timeout.
            if process.poll() is None:
                kill_group(process)
                process.wait()
        size = os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size
        if size > max_bytes and failure is None:
            failure = "output_limit"
        stdout = os.pread(out.fileno(), max_bytes, 0).decode(errors="replace")
        stderr = os.pread(err.fileno(), max_bytes, 0).decode(errors="replace")
        if max_tool_calls is not None and count_tool_calls(stdout) > max_tool_calls and failure is None:
            failure = "tool_limit"
    return ProcessResult(process.returncode, redact(stdout), redact(stderr), time.monotonic() - started, failure)
