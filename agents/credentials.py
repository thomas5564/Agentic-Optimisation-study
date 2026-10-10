"""Load only named SOCLAAS settings without sourcing executable shell text."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import runpy
import shlex
import sys

NAMES = {"SOCLAAS_BASE_URL", "SOCLAAS_API_KEY", "SOCLAAS_MODEL"}


def load_credentials(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.removeprefix("export ").partition("=")
        key = key.strip()
        if not separator or key not in NAMES or key in values:
            raise ValueError("Credential file contains an unexpected or duplicate setting")
        parts = shlex.split(value, comments=True)
        if len(parts) != 1 or not parts[0]:
            raise ValueError("Credential setting must have one nonempty value")
        values[key] = parts[0]
    if set(values) != NAMES:
        raise ValueError("Credential file must define all three SOCLAAS settings")
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--module", choices=["controller.run", "controller.batch", "controller.resume", "agents.preflight"], required=True)
    args, remaining = parser.parse_known_args()
    try:
        os.environ.update(load_credentials(args.file))
    except (ValueError, OSError):
        parser.exit(2, "Cannot load the SOCLAAS credential file; verify its three settings.\n")
    sys.argv = [args.module, *([*remaining[1:]] if remaining[:1] == ["--"] else remaining)]
    runpy.run_module(args.module, run_name="__main__")


if __name__ == "__main__":
    main()
