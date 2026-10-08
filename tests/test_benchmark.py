from benchmarks.oracle import validate_create_response, validate_list_response
from benchmarks.reset import reset_database


def test_seeded_reset_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTES_DB_PATH", str(tmp_path / "benchmark.db"))
    first = reset_database(seed=11, count=5)
    second = reset_database(seed=11, count=5)
    assert first == second
    assert len(first) == 5


def test_oracle_detects_bad_response():
    expected = {"items": [{"id": 1, "title": "Alpha", "body": "Body", "tags": ["x"]}], "total": 1}
    bad = {"items": [{"id": 1, "title": "Wrong", "body": "Body", "tags": ["x"]}], "total": 1}
    assert validate_list_response(expected, 1, ["Alpha"]) is True
    assert validate_list_response(bad, 1, ["Alpha"]) is False

    good_create = {"id": 1, "title": "Alpha", "body": "Body", "tags": ["x"]}
    wrong_create = {"id": 1, "title": "Beta", "body": "Body", "tags": ["x"]}
    assert validate_create_response(good_create, "Alpha", "Body") is True
    assert validate_create_response(wrong_create, "Alpha", "Body") is False
