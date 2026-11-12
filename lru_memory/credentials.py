"""Load SOCLAAS settings as data (never sourced) and run a three-arm module with them."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import runpy
import sys

from agents.credentials import load_credentials

MODULES = ["lru_memory.run", "lru_memory.batch", "lru_memory.resume", "agents.preflight"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--module", choices=MODULES, required=True)
    args, remaining = parser.parse_known_args()
    try:
        os.environ.update(load_credentials(args.file))
    except (ValueError, OSError):
        parser.exit(2, "Cannot load the SOCLAAS credential file; verify its three settings.\n")
    sys.argv = [args.module, *(remaining[1:] if remaining[:1] == ["--"] else remaining)]
    runpy.run_module(args.module, run_name="__main__")


if __name__ == "__main__":
    main()
