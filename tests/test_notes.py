import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "notes.db"
    monkeypatch.setenv("NOTES_DB_PATH", str(db_path))

    import app.main

    importlib.reload(app.main)
    return TestClient(app.main.app)


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

    import app.main as app_module

    fresh_client = TestClient(app_module.app)
    persisted = fresh_client.get(f"/notes/{note_id}")
    assert persisted.status_code == 200
    assert persisted.json()["title"] == "Persist"


def test_seed_database_is_deterministic():
    import app.seed

    first = app.seed.seed_database(7, 3)
    second = app.seed.seed_database(7, 3)

    assert first == second
    assert len(first) == 3
    assert all(note["id"] for note in first)
