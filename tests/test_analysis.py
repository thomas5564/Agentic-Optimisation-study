import json
from pathlib import Path

import pytest

from analysis.report import load_runs, report, stats, summarize
from benchmarks.metrics import write_json
from controller.engine import Engine, initialize_run
from test_controller import RecordingBackend, SyntheticEvaluator, config


def make_run(root, condition, pair_id="0", cases=None):
    cfg = config(cases or ["broken", "noop"], checkpoints=[1,2])
    initialize_run(root, cfg, "mock", condition, 2, synthetic=True, pair_id=pair_id)
    Engine(root, RecordingBackend(), SyntheticEvaluator()).run()


def test_identical_and_all_failed_candidates_are_explicit(tmp_path):
    make_run(tmp_path / "stateless", "stateless")
    make_run(tmp_path / "memory", "memory")
    runs = load_runs(tmp_path)
    summary, attempts, requests, repetitions, checkpoints = summarize(runs)
    assert summary["paired_final_comparisons"][0]["stateless_over_memory_speedup"] == 1
    assert all(row["accepted_changes"] == 0 for row in summary["runs"])
    assert all(row["correctness_pass_rate"] == 0 for row in summary["runs"])
    assert all(row["cost_usd"] is None and row["input_tokens"] is None for row in summary["runs"])
    assert all(row["candidate_request_success_rate"] is None for row in attempts)
    assert len(checkpoints) == 4
    assert stats([]) == {"n_runs":0,"mean":None,"sample_sd":None,"min":None,"max":None}
    assert stats([1])["sample_sd"] is None
    result = report(tmp_path, tmp_path / "report", make_figures=False)
    assert result["run_count"] == 2
    assert len(result["cohorts"]) == 1
    content = (tmp_path / "report" / result["cohorts"][0] / "attempts.csv").read_text()
    assert "synthetic" in content and "carried_forward" in content


def test_independent_runs_not_iterations_supply_uncertainty(tmp_path):
    make_run(tmp_path / "first", "memory", "0", ["faster", "faster"])
    make_run(tmp_path / "second", "memory", "1", ["faster", "faster"])
    summary, *_ = summarize(load_runs(tmp_path))
    assert all(point["n_runs"] == 2 for point in summary["trajectories"])
    assert all(point["sample_sd"] == 0 for point in summary["trajectories"])


def test_incomplete_pair_has_no_comparative_speedup(tmp_path):
    make_run(tmp_path / "first", "stateless")
    summary, *_ = summarize(load_runs(tmp_path))
    assert summary["paired_final_comparisons"][0]["stateless_over_memory_speedup"] is None


def test_separate_cohorts_for_synthetic_and_measured(tmp_path):
    make_run(tmp_path / "first", "memory")
    make_run(tmp_path / "second", "stateless")
    manifest = json.loads((tmp_path / "second" / "manifest.json").read_text())
    manifest["synthetic"] = False
    write_json(tmp_path / "second" / "manifest.json", manifest)
    result = report(tmp_path, tmp_path / "report", make_figures=False)
    assert len(result["cohorts"]) == 2


def test_duplicate_run_copies_not_counted_as_replicates(tmp_path):
    import shutil
    make_run(tmp_path / "first", "stateless")
    shutil.copytree(tmp_path / "first", tmp_path / "copy")
    with pytest.raises(ValueError, match="Duplicate run IDs"):
        load_runs(tmp_path)
