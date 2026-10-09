from __future__ import annotations

from contextlib import contextmanager
import difflib
import fcntl
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from benchmarks.metrics import write_json
from benchmarks.run import content_hash


def read_json(path: Path):
    return json.loads(path.read_text())


def app_hash(files: dict[str, str]) -> str:
    return content_hash({name: hashlib.sha256(text.encode()).hexdigest()
                         for name, text in sorted(files.items()) if name.startswith("app/")})


def safe_path(name: str, app_only: bool = False):
    path = PurePosixPath(name)
    if ("\\" in name or path.is_absolute() or name != path.as_posix()
            or any(p in {"", ".", ".."} or p.startswith(".") for p in path.parts)
            or not path.parts or path.parts[0] not in ({"app"} if app_only else {"app", "contracts"})
            or "__pycache__" in path.parts or path.suffix not in {".py", ".html", ".css", ".js", ".md", ".json"}):
        raise ValueError(f"Disallowed patch/snapshot path: {name}")
    if app_only and (path.suffix in {".md", ".json"} or path.name in {"conftest.py", "sitecustomize.py", "usercustomize.py"}):
        raise ValueError(f"Disallowed application file: {name}")


def load_baseline(directory: Path) -> dict[str, str]:
    manifest = read_json(directory / "manifest.json")
    archive = directory / "source.zip"
    if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest["archive_sha256"]:
        raise ValueError("Baseline archive hash mismatch")
    files = {}
    with zipfile.ZipFile(archive) as handle:
        if set(handle.namelist()) != set(manifest["files"]) or len(handle.namelist()) != len(manifest["files"]):
            raise ValueError("Baseline archive manifest mismatch")
        for name in handle.namelist():
            safe_path(name)
            data = handle.read(name)
            if hashlib.sha256(data).hexdigest() != manifest["files"][name]:
                raise ValueError("Baseline file hash mismatch")
            files[name] = data.decode()
    if app_hash(files) != manifest["source"]["sha256"]:
        raise ValueError("Baseline source hash mismatch")
    return files


def apply_edits(parent: dict, edits: list[dict], max_bytes: int) -> dict:
    result = dict(parent)
    seen = set()
    for edit in edits:
        name = edit["path"]
        safe_path(name, app_only=True)
        if name in seen:
            raise ValueError("Duplicate patch path")
        seen.add(name)
        if edit["content"] is None:
            if name not in result:
                raise ValueError("Cannot delete a missing file")
            del result[name]
        else:
            if re.search(r"\bpragma\s+(?:synchronous\s*=\s*(?:off|0)|journal_mode\s*=\s*(?:off|memory))\b", edit["content"], re.IGNORECASE):
                raise ValueError("Patch explicitly disables SQLite durability")
            result[name] = edit["content"]
    if not {"app/__init__.py", "app/main.py"} <= result.keys():
        raise ValueError("Patch removed application entry points")
    if sum(len(text.encode()) for text in result.values()) > max_bytes:
        raise ValueError("Candidate exceeds configured size budget")
    return result


def save_snapshot(run_dir: Path, files: dict) -> str:
    digest = app_hash(files)
    path = run_dir / "snapshots" / f"{digest}.json"
    if path.exists():
        if read_json(path) != files:
            raise ValueError("Snapshot identity conflict or contract changed")
    else:
        write_json(path, files)
    return digest


def load_snapshot(run_dir: Path, digest: str) -> dict:
    files = read_json(run_dir / "snapshots" / f"{digest}.json")
    if app_hash(files) != digest:
        raise ValueError("Snapshot hash mismatch")
    return files


@contextmanager
def workspace(files: dict):
    with tempfile.TemporaryDirectory(prefix="notes-candidate-") as directory:
        root = Path(directory)
        for name, text in files.items():
            safe_path(name)
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        yield root


@contextmanager
def run_lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("This run is already active") from error
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def patch_diff(parent: dict, candidate: dict) -> str:
    return "".join("".join(difflib.unified_diff(parent.get(name, "").splitlines(True),
                    candidate.get(name, "").splitlines(True), fromfile=f"a/{name}", tofile=f"b/{name}"))
                   for name in sorted(set(parent) | set(candidate)) if parent.get(name) != candidate.get(name))
