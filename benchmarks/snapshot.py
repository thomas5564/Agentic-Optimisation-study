"""Preserve a clean baseline containing only application code and public contract."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import zipfile

from benchmarks.metrics import write_json
from benchmarks.run import environment, source_manifest
from benchmarks.runtime import PROJECT_ROOT


def freeze_baseline(output: Path, root: Path = PROJECT_ROOT) -> dict:
    if output.exists():
        raise ValueError("Baseline destination already exists; do not replace a frozen baseline")
    files = []
    for directory in (root / "app", root / "contracts"):
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Symlinks are not allowed in baseline: {path}")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                files.append(path)
    if not files or not (root / "contracts" / "API.md").exists():
        raise ValueError("Application and public contract are required")
    output.mkdir(parents=True)
    archive = output / "source.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_STORED) as handle:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(root).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            handle.writestr(info, path.read_bytes())
    manifest = {"schema_version": 1, "kind": "frozen_baseline", "source": source_manifest(root),
                "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "environment": environment(),
                "files": {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                "dependency_lock_sha256": hashlib.sha256((root / "requirements.lock").read_bytes()).hexdigest()}
    write_json(output / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = freeze_baseline(args.output)
    print(result["source"]["sha256"])


if __name__ == "__main__":
    main()
