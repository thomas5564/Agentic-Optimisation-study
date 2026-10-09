"""Containers expose only explicit current-role inputs, never the project/home."""
from __future__ import annotations

import os
from pathlib import Path
import uuid

from agents.process import run_process


class PrerequisiteError(RuntimeError):
    pass


def mount(source: Path, target: str, readonly: bool = True) -> list[str]:
    source = source.resolve()
    if "," in str(source):
        raise ValueError("Docker mount paths cannot contain commas")
    return ["--mount", f"type=bind,src={source},dst={target}" + (",readonly" if readonly else "")]


def container_command(image: str, name: str, network: str = "none") -> list[str]:
    if not image.startswith("sha256:"):
        raise PrerequisiteError("Use an immutable Docker image ID (sha256:...), not a mutable tag")
    if network in {"host", "container"} or network.startswith("container:"):
        raise PrerequisiteError("Host/shared container networking is forbidden")
    return ["docker", "run", "-i", "--rm", "--name", name, "--init", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=128",
            "--memory=2g", "--cpus=1", "--network", network,
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--tmpfs", "/tmp:rw,nosuid,nodev,mode=1777,size=512m",
            "--env", "HOME=/tmp/home", "--env", "CODEX_HOME=/tmp/codex",
            "--env", "PYTHONDONTWRITEBYTECODE=1", "--workdir", "/workspace"]


def remove_container(name: str):
    # Docker client termination does not necessarily stop its daemon-owned container.
    run_process(["docker", "rm", "-f", name], timeout=10)


def inspect_image(image: str) -> dict:
    if not image or not image.startswith("sha256:"):
        raise PrerequisiteError("Configure an immutable container image ID before live execution")
    try:
        daemon = run_process(["docker", "version", "--format", "{{.Server.Version}}"], timeout=10)
        if daemon.returncode:
            raise PrerequisiteError("Docker daemon is unavailable; start Docker and build the experiment image")
        installed = run_process(["docker", "image", "inspect", image, "--format", "{{.Id}}"], timeout=10)
        if installed.returncode or installed.stdout.strip() != image:
            raise PrerequisiteError("Configured image is missing; build it locally and record its exact image ID")
        return {"docker_server": daemon.stdout.strip(), "image_id": image}
    except FileNotFoundError as error:
        raise PrerequisiteError("Docker CLI is not installed") from error
