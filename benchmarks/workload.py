from __future__ import annotations

from typing import Any

from app.seed import seed_database


def build_workload(seed: int = 7, note_count: int = 20) -> list[dict[str, Any]]:
    """Build a deterministic request plan for the notes workload."""
    fixture = seed_database(seed, note_count)
    first_note = fixture[0]
    second_note = fixture[1] if len(fixture) > 1 else fixture[0]
    return [
        {
            "name": "list_initial",
            "method": "GET",
            "path": "/notes",
            "params": {"limit": 10},
            "expected_total": note_count,
        },
        {
            "name": "create_note",
            "method": "POST",
            "path": "/notes",
            "payload": {
                "title": "Benchmark note",
                "body": "Created during benchmark workload",
                "tags": ["benchmark", "workload"],
            },
            "expected_title": "Benchmark note",
            "expected_body": "Created during benchmark workload",
        },
        {
            "name": "search_notes",
            "method": "GET",
            "path": "/notes",
            "params": {"q": str(first_note["title"]).lower(), "limit": 10},
            "expected_total": 1,
            "expected_titles": [str(first_note["title"])],
        },
        {
            "name": "update_note",
            "method": "PUT",
            "path": f"/notes/{second_note['id']}",
            "payload": {
                "title": "Updated benchmark title",
                "body": "Updated body for benchmark validation",
                "tags": ["updated", "bench"],
            },
            "expected_title": "Updated benchmark title",
            "expected_body": "Updated body for benchmark validation",
        },
        {
            "name": "delete_note",
            "method": "DELETE",
            "path": f"/notes/{first_note['id']}",
            "expected_status": 204,
        },
    ]
