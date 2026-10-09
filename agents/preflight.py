"""Read-only CLI checks plus a real, unpaid container boundary probe."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import uuid

from agents.codex import inspect_cli
from agents.docker import PrerequisiteError, container_command, mount, remove_container
from agents.process import run_process
from controller.config import load_config


def isolation_probe(config) -> dict:
    with tempfile.TemporaryDirectory(prefix="notes-isolation-probe-") as directory:
        base = Path(directory)
        current, incoming, output = base / "current", base / "input", base / "output"
        for path in (current / "app", current / "contracts", incoming, output):
            path.mkdir(parents=True)
        (current / "app" / "__init__.py").write_text("# probe\n")
        (current / "contracts" / "API.md").write_text("contract")
        (incoming / "schema.json").write_text("{}")
        sentinel = base / "researcher-history.txt"
        sentinel.write_text("private-history-sentinel")
        script = '''import json, os
from pathlib import Path
sentinel = Path(SENTINEL)
assert not sentinel.exists(), 'host/sibling history exposed'
for path in ['/workspace/.git', '/workspace/docs', '/workspace/tests', '/workspace/benchmarks', '/tmp/codex/sessions']:
    assert not Path(path).exists(), path
for path in ['/workspace/app/__init__.py', '/workspace/contracts/API.md', '/input/schema.json']:
    try:
        Path(path).write_text('forbidden')
    except OSError:
        pass
    else:
        raise AssertionError('read-only mount writable: ' + path)
Path('/result/probe.txt').write_text('allowed')
assert 'CODEX_API_KEY' not in os.environ
print(json.dumps({'host_and_sibling_denied': True, 'history_absent': True, 'app_contract_inputs_readonly': True, 'output_writable': True}))
'''.replace("SENTINEL", repr(str(sentinel)))
        name = "notes-probe-" + uuid.uuid4().hex
        command = container_command(config.image, name)
        command += mount(current, "/workspace") + mount(incoming, "/input") + mount(output, "/result", False)
        command += [config.image, "python", "-c", script]
        try:
            result = run_process(command, timeout=30)
        finally:
            remove_container(name)
        if result.returncode or result.failure:
            raise PrerequisiteError("Container boundary probe failed: " + result.stderr)
        return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        evidence = inspect_cli(config)
        evidence["isolation_probe"] = isolation_probe(config)
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
