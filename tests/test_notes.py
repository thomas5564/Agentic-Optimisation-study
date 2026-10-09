import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import os
    if os.environ.get("NOTES_EVALUATION_ROOT"):
        from pathlib import Path
        from benchmarks.config import BenchmarkConfig
        from benchmarks.runtime import candidate_server
        with candidate_server(Path(os.environ["NOTES_EVALUATION_ROOT"]), BenchmarkConfig(), tmp_path / "server.log") as (remote, _):
            yield remote
        return
    db_path = tmp_path / "notes.db"
    monkeypatch.setenv("NOTES_DB_PATH", str(db_path))

    import app.main

    importlib.reload(app.main)
    with TestClient(app.main.app) as local:
        yield local


def test_create_and_get_note(client):
    response = client.post(
        "/notes",
        json={
            "title": "Alpha",
            "body": "First note body",
            "tags": ["work", "alpha"],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["title"] == "Alpha"
    assert payload["body"] == "First note body"
    assert payload["tags"] == ["alpha", "work"]
    assert payload["id"] == 1

    get_response = client.get("/notes/1")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == 1


def test_search_filter_pagination(client):
    client.post("/notes", json={"title": "Alpha", "body": "Red apple", "tags": ["fruit", "red"]})
    client.post("/notes", json={"title": "Beta", "body": "Green berry", "tags": ["fruit", "green"]})
    client.post("/notes", json={"title": "Gamma", "body": "Blue sky", "tags": ["color"]})

    response = client.get("/notes", params={"q": "apple", "tag": "fruit", "limit": 10})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [note["title"] for note in body["items"]] == ["Alpha"]

    paginated = client.get("/notes", params={"offset": 1, "limit": 1})
    assert paginated.status_code == 200
    assert paginated.json()["total"] == 3
    assert paginated.json()["items"][0]["id"] == 2


def test_update_delete_and_missing_ids(client):
    create = client.post("/notes", json={"title": "Old", "body": "Before", "tags": ["old"]})
    note_id = create.json()["id"]

    update = client.put(
        f"/notes/{note_id}",
        json={"title": "New", "body": "After", "tags": ["new", "fresh"]},
    )
    assert update.status_code == 200
    assert update.json()["title"] == "New"

    deleted = client.delete(f"/notes/{note_id}")
    assert deleted.status_code == 204
    assert client.get(f"/notes/{note_id}").status_code == 404
    assert client.get("/notes/9999").status_code == 404


def test_validation_and_invalid_filters(client):
    bad = client.post("/notes", json={"title": "", "body": "Oops"})
    assert bad.status_code == 422

    invalid_limit = client.get("/notes", params={"limit": 0})
    assert invalid_limit.status_code == 422

    invalid_offset = client.get("/notes", params={"offset": -1})
    assert invalid_offset.status_code == 422

    bad_search = client.get("/notes", params={"tag": "", "q": ""})
    assert bad_search.status_code == 200


def test_persistence_after_restart(client, tmp_path, monkeypatch):
    response = client.post("/notes", json={"title": "Persist", "body": "Survive reboot", "tags": ["save"]})
    note_id = response.json()["id"]

    import os
    if os.environ.get("NOTES_EVALUATION_ROOT"):
        # The dedicated process restart test below covers actual restart persistence.
        assert client.get(f"/notes/{note_id}").json()["title"] == "Persist"
        return

    import app.main as app_module

    fresh_client = TestClient(app_module.app)
    persisted = fresh_client.get(f"/notes/{note_id}")
    assert persisted.status_code == 200
    assert persisted.json()["title"] == "Persist"


def test_seed_database_is_deterministic():
    import os
    if os.environ.get("NOTES_EVALUATION_ROOT"):
        import json
        import subprocess
        import sys
        result = subprocess.run([sys.executable, "-c", "import json; from app.seed import seed_database; print(json.dumps([seed_database(7,3),seed_database(7,3)]))"],
                                cwd=os.environ["NOTES_EVALUATION_ROOT"], check=True, capture_output=True, text=True, timeout=10)
        first, second = json.loads(result.stdout)
        assert first == second and len(first) == 3 and all(n["id"] for n in first)
        return
    import app.seed

    first = app.seed.seed_database(7, 3)
    second = app.seed.seed_database(7, 3)

    assert first == second
    assert len(first) == 3
    assert all(note["id"] for note in first)


def test_case_sensitive_exact_filters_unicode_and_parameterization(client):
    payload = {"title": "Café 世界", "body": "100%_literal ' OR 1=1 --", "tags": ["Work", "work", " Work ", ""]}
    created = client.post("/notes", json=payload).json()
    assert created["tags"] == ["Work", "work"]
    client.post("/notes", json={"title": "Other", "body": "other", "tags": ["work"]})
    assert client.get("/notes", params={"q": "Café"}).json()["total"] == 1
    assert client.get("/notes", params={"q": "café"}).json()["total"] == 0
    assert client.get("/notes", params={"q": "%_literal"}).json()["total"] == 1
    assert client.get("/notes", params={"q": "' OR 1=1 --"}).json()["total"] == 1
    assert client.get("/notes", params={"tag": "Work"}).json()["total"] == 1
    assert client.get("/notes", params={"tag": ["Work", "work"]}).json()["total"] == 1
    assert client.get("/notes", params={"q": "Other", "tag": "Work"}).json()["total"] == 0
    assert client.get("/notes", params={"q": ""}).json()["total"] == 2
    assert client.get("/notes", params={"offset": 50}).json() == {"items": [], "total": 2, "offset": 50, "limit": 20}


def test_read_and_filter_cache_invalidation(client):
    created = client.post("/notes", json={"title": "Before", "body": "Body", "tags": ["old"]}).json()
    note_id = created["id"]
    assert client.get(f"/notes/{note_id}").json() == created
    assert client.get("/notes", params={"tag": "old"}).json()["total"] == 1
    updated = client.put(f"/notes/{note_id}", json={"title": "After", "body": "New body", "tags": ["new"]}).json()
    assert client.get(f"/notes/{note_id}").json() == updated
    assert client.get("/notes", params={"tag": "old"}).json()["total"] == 0
    assert client.get("/notes", params={"q": "After", "tag": "new"}).json()["items"] == [updated]
    client.delete(f"/notes/{note_id}")
    assert client.get(f"/notes/{note_id}").json() == {"detail": "Note not found"}
    assert client.get("/notes", params={"tag": "new"}).json()["total"] == 0


@pytest.mark.parametrize("payload", [
    {}, {"title": "A", "body": ""}, {"title": "A" * 201, "body": "B"},
    {"title": "A", "body": "B" * 5001}, {"title": 1, "body": "B"},
    {"title": "A", "body": "B", "tags": [1]},
])
def test_validation_boundaries(client, payload):
    result = client.post("/notes", json=payload)
    assert result.status_code == 422
    assert isinstance(result.json()["detail"], list)
    assert client.get("/notes").json()["total"] == 0


def test_missing_updates_deletes_and_invalid_ids(client):
    assert client.put("/notes/999", json={"title": "T", "body": "B"}).json() == {"detail": "Note not found"}
    assert client.delete("/notes/999").status_code == 404
    assert client.get("/notes/not-an-integer").status_code == 422
    assert client.get("/notes", params={"limit": 101}).status_code == 422


def test_mutations_survive_real_process_restart(tmp_path):
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys

    if os.environ.get("NOTES_EVALUATION_ROOT"):
        from benchmarks.config import BenchmarkConfig
        from benchmarks.runtime import candidate_server
        root = Path(os.environ["NOTES_EVALUATION_ROOT"])
        db = tmp_path / "persist.db"
        with candidate_server(root, BenchmarkConfig(), tmp_path / "before.log", database=db) as (remote, _):
            a = remote.post("/notes", json={"title": "Before", "body": "Body", "tags": ["old"]}).json()
            b = remote.post("/notes", json={"title": "Delete", "body": "Body"}).json()
            updated = remote.put(f"/notes/{a['id']}", json={"title": "Persist 世界", "body": "Changed", "tags": ["new"]}).json()
            assert remote.delete(f"/notes/{b['id']}").status_code == 204
        with candidate_server(root, BenchmarkConfig(), tmp_path / "after.log", database=db) as (remote, _):
            assert remote.get(f"/notes/{a['id']}").json() == updated
            assert remote.get(f"/notes/{b['id']}").status_code == 404
            assert remote.get("/notes").json()["total"] == 1
        return

    env = {**os.environ, "NOTES_DB_PATH": str(tmp_path / "persist.db"), "PYTHONDONTWRITEBYTECODE": "1"}
    setup = '''from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    a = client.post('/notes', json={'title':'Before','body':'Body','tags':['old']}).json()
    b = client.post('/notes', json={'title':'Delete','body':'Body'}).json()
    client.put(f"/notes/{a['id']}", json={'title':'Persist 世界','body':'Changed','tags':['new']})
    client.delete(f"/notes/{b['id']}")
'''
    check = '''import json
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    print(json.dumps({'note':client.get('/notes/1').json(), 'deleted':client.get('/notes/2').status_code, 'total':client.get('/notes').json()['total']}))
'''
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, "-c", setup], env=env, cwd=root, check=True, capture_output=True)
    result = subprocess.run([sys.executable, "-c", check], env=env, cwd=root, check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == {"note": {"id": 1, "title": "Persist 世界", "body": "Changed", "tags": ["new"]}, "deleted": 404, "total": 1}


def test_frozen_validation_responses(client):
    import json
    from pathlib import Path
    fixtures = json.loads((Path(__file__).resolve().parents[1] / "contracts" / "validation-errors.json").read_text())
    for case in fixtures["cases"]:
        response = client.request(**case["request"])
        assert response.status_code == case["status_code"]
        assert response.json() == case["response"]
