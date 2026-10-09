from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import httpx
import pytest

from benchmarks.config import BenchmarkConfig
from benchmarks.fixtures import make_fixture
from benchmarks.metrics import aggregate_runs, summarize_samples, write_json
from benchmarks.oracle import Oracle
from benchmarks.reset import reset_database
from benchmarks.run import execute_trace, run_once, source_manifest
from benchmarks.runtime import PROJECT_ROOT, benchmark_lock, candidate_server
from benchmarks.workload import build_workload


def seeded_oracle():
    oracle = Oracle()
    note = {"id": 17, "title": "Alpha", "body": "Body 世界", "tags": ["x"]}
    assert oracle.check({"method": "POST", "bind": "first", "payload": note}, 201, note)
    return oracle, note


def test_oracle_rejects_wrong_fields_and_stale_cache():
    oracle, note = seeded_oracle()
    listing = {"items": [note], "total": 1, "offset": 0, "limit": 20}
    assert oracle.check({"method": "GET"}, 200, listing)
    for field, value in (("body", "wrong"), ("tags", ["bad"]), ("id", True)):
        bad = deepcopy(listing)
        bad["items"][0][field] = value
        assert not oracle.check({"method": "GET"}, 200, bad)
    for field in ("offset", "limit", "total"):
        bad = {**listing, field: 99}
        assert not oracle.check({"method": "GET"}, 200, bad)
    updated = {**note, "title": "Revised", "tags": ["new"]}
    assert oracle.check({"method": "PUT", "ref": "first", "payload": updated}, 200, updated)
    assert not oracle.check({"method": "GET", "ref": "first"}, 200, note)
    assert not oracle.check({"method": "GET"}, 200, listing)
    assert oracle.check({"method": "DELETE", "ref": "first"}, 204, None)
    assert not oracle.check({"method": "GET", "ref": "first"}, 200, updated)
    assert oracle.check({"method": "GET", "ref": "first"}, 404, {"detail": "Note not found"})


def test_oracle_does_not_trust_create_ids_or_duplicate_ids():
    oracle, note = seeded_oracle()
    for value in (True, "18", 18.0, 17):
        assert not oracle.check({"method": "POST", "bind": "new", "payload": note}, 201, {**note, "id": value})


def test_failures_and_dependencies_cannot_produce_a_score():
    def respond(request):
        if request.method == "POST":
            raise httpx.ReadTimeout("test timeout", request=request)
        return httpx.Response(200, json={"items": [], "total": 0, "offset": 0, "limit": 20})
    trace = [
        {"name": "create", "operation": "add", "method": "POST", "bind": "new", "payload": {"title": "T", "body": "B"}},
        {"name": "get", "operation": "get", "method": "GET", "ref": "new"},
        {"name": "list", "operation": "list_search", "method": "GET"},
    ]
    with httpx.Client(transport=httpx.MockTransport(respond), base_url="http://test") as client:
        result = execute_trace(client, Oracle(), trace)
    assert result["score_ms"] is None
    assert result["counts"]["total"] == 3
    assert result["counts"]["failed"] == 2
    assert result["counts"]["timed_out"] == 1
    assert result["requests"][1]["error"] == "failed_dependency"
    assert result["requests"][1]["elapsed_ms"] is None
    assert aggregate_runs([result])["score_ms"] is None


def test_invalid_response_has_no_score():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="not JSON")), base_url="http://test") as client:
        result = execute_trace(client, Oracle(), [{"name": "list", "operation": "list_search", "method": "GET"}])
    assert result["counts"]["semantic_mismatches"] == 1
    assert result["score_ms"] is None


def test_score_uses_median_of_repetition_means_and_null_for_missing():
    runs = [{"score_ms": score, "requests": []} for score in (1., 3., 20.)]
    assert aggregate_runs(runs)["score_ms"] == 3
    assert aggregate_runs(runs + [{"score_ms": None, "requests": []}])["score_ms"] is None
    assert summarize_samples([])["mean"] is None
    assert summarize_samples(list(range(1, 21)))["p95"] == 19


@pytest.mark.parametrize("kwargs", [{"warmups": -1}, {"cycles": 0}, {"note_count": 0}, {"concurrency": 2}, {"timeout_seconds": float("nan")}, {"repetitions": True}])
def test_invalid_settings_rejected(kwargs):
    with pytest.raises(ValueError):
        BenchmarkConfig(**kwargs)


def test_lock_rejects_overlap():
    with benchmark_lock():
        with pytest.raises(RuntimeError, match="serial"):
            with benchmark_lock():
                pass


def test_atomic_json_preserves_previous_file_if_serialization_fails(tmp_path):
    path = tmp_path / "result.json"
    write_json(path, {"score_ms": None})
    with pytest.raises(ValueError):
        write_json(path, {"score_ms": float("nan")})
    assert json.loads(path.read_text()) == {"score_ms": None}


def test_real_repetitions_reset_state_and_preserve_developer_database(tmp_path, monkeypatch):
    protected = tmp_path / "developer.db"
    protected.write_bytes(b"Do not touch")
    monkeypatch.setenv("NOTES_DB_PATH", str(protected))
    config = BenchmarkConfig(note_count=3, cycles=2, warmups=1, repetitions=2)
    before = source_manifest(PROJECT_ROOT)
    first = run_once(config, PROJECT_ROOT, tmp_path / "first.log")
    second = run_once(config, PROJECT_ROOT, tmp_path / "second.log")
    assert first["error"] is None, first
    assert second["error"] is None, second
    assert first["score_ms"] > 0 and second["score_ms"] > 0
    assert first["logical_fixture_hash"] == second["logical_fixture_hash"]
    assert len(first["requests"]) == 24
    assert len(first["warmups"][0]["requests"]) == 2
    assert protected.read_bytes() == b"Do not touch"
    assert source_manifest(PROJECT_ROOT) == before
    assert build_workload(7, 3, 2) == build_workload(7, 3, 2)
    assert make_fixture(7, 3) == make_fixture(7, 3)


def test_candidate_schema_indexes_survive_api_seeding(tmp_path):
    root = tmp_path / "candidate"
    shutil.copytree(PROJECT_ROOT / "app", root / "app", ignore=shutil.ignore_patterns("__pycache__"))
    db = root / "app" / "db.py"
    db.write_text(db.read_text().replace("    connection.commit()", "    connection.execute('CREATE INDEX IF NOT EXISTS title_idx ON notes(title)')\n    connection.commit()"))
    # Make the candidate refuse reads unless its own schema initialization ran.
    db.write_text(db.read_text().replace('    rows = connection.execute("SELECT * FROM notes ORDER BY id ASC").fetchall()',
        '    assert connection.execute("SELECT name FROM sqlite_master WHERE name = \'title_idx\'").fetchone()\n    rows = connection.execute("SELECT * FROM notes ORDER BY id ASC").fetchall()'))
    result = run_once(BenchmarkConfig(note_count=2, cycles=1), root, tmp_path / "index.log")
    assert result["score_ms"] is not None, result


def test_real_http_timeout_is_counted(tmp_path):
    root = tmp_path / "candidate"
    (root / "app").mkdir(parents=True)
    (root / "app" / "__init__.py").write_text("")
    (root / "app" / "main.py").write_text('from fastapi import FastAPI\nimport time\napp=FastAPI()\n@app.get("/notes")\ndef listing():\n    return {}\n@app.get("/notes/{note_id}")\ndef slow(note_id: int):\n    time.sleep(.2)\n    return {}\n')
    config = BenchmarkConfig(timeout_seconds=.03)
    oracle, _ = seeded_oracle()
    with candidate_server(root, config, tmp_path / "slow.log") as (client, _):
        started = time.monotonic()
        result = execute_trace(client, oracle, [{"name": "slow", "method": "GET", "ref": "first", "operation": "get"}])
        assert time.monotonic() - started < 1
    assert result["counts"]["timed_out"] == 1
    assert result["score_ms"] is None


def test_import_failure_is_recorded(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "main.py").write_text("raise RuntimeError('broken candidate')")
    result = run_once(BenchmarkConfig(), tmp_path, tmp_path / "broken.log")
    assert result["startup_status"] == "failed"
    assert result["score_ms"] is None
    assert "broken candidate" in (tmp_path / "broken.log").read_text()


def test_profile_contains_application_work_and_no_acceptance_score(tmp_path):
    import pstats
    raw = tmp_path / "application.prof"
    result = run_once(BenchmarkConfig(note_count=2, cycles=1, warmups=1), PROJECT_ROOT, tmp_path / "profile.log", raw)
    assert result["error"] is None, result
    assert result["score_ms"] is None
    stats = pstats.Stats(str(raw))
    app_functions = {key[2] for key in stats.stats if "/app/" in key[0]}
    assert {"list_notes", "get_note", "create_note", "update_note", "delete_note"} <= app_functions
    # Fixture creation and warmups are excluded from profiling.
    calls = sum(value[1] for key, value in stats.stats.items() if key[2] == "create_note" and key[0].endswith("app/db.py"))
    assert calls == 1


def test_missing_candidate_cannot_fall_back_to_development_app(tmp_path):
    result = run_once(BenchmarkConfig(), tmp_path, tmp_path / "missing.log")
    assert result["score_ms"] is None
    assert result["startup_status"] == "failed"


def test_frozen_snapshot_has_only_allowlisted_content_and_verifiable_hashes(tmp_path):
    import hashlib
    import zipfile
    from benchmarks.snapshot import freeze_baseline
    root = tmp_path / "baseline"
    manifest = freeze_baseline(root)
    assert hashlib.sha256((root / "source.zip").read_bytes()).hexdigest() == manifest["archive_sha256"]
    with zipfile.ZipFile(root / "source.zip") as archive:
        assert set(archive.namelist()) == set(manifest["files"])
        for name in archive.namelist():
            assert name.split("/")[0] in {"app", "contracts"}
            assert "__pycache__" not in name
            assert hashlib.sha256(archive.read(name)).hexdigest() == manifest["files"][name]
    with pytest.raises(ValueError, match="already exists"):
        freeze_baseline(root)
