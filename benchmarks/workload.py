"""Fixed request dependencies; generated IDs are bound by the response oracle."""
from __future__ import annotations

from benchmarks.fixtures import make_fixture


def build_warmup() -> list[dict]:
    # Read-only: the timed trace always starts with exactly the seeded logical state.
    return [
        {"name": "warm_get", "operation": "get", "method": "GET", "ref": "seed_0"},
        {"name": "warm_list", "operation": "list_search", "method": "GET",
         "params": {"limit": 20}},
    ]


def build_workload(seed: int = 7, note_count: int = 20, cycles: int = 20) -> list[dict]:
    fixture = make_fixture(seed, note_count)
    if not fixture or cycles < 1:
        raise ValueError("note_count and cycles must be positive")
    trace = []
    for i in range(cycles):
        ref = f"created_{i}"
        initial = {"title": f"Workload {i}", "body": "Created café 世界", "tags": ["workload"]}
        updated = {"title": f"Revised {i}", "body": "Updated ' OR 1=1 --", "tags": ["changed"]}
        steps = [
            {"operation": "get", "method": "GET", "ref": f"seed_{i % note_count}"},
            {"operation": "list_search", "method": "GET", "params": {"offset": i % note_count, "limit": 10}},
            {"operation": "list_search", "method": "GET", "params": {"q": fixture[i % note_count]["title"], "tag": fixture[i % note_count]["tags"], "limit": 10}},
            {"operation": "add", "method": "POST", "bind": ref, "payload": initial},
            {"operation": "get", "method": "GET", "ref": ref},
            {"operation": "list_search", "method": "GET", "params": {"tag": "workload"}},
            {"operation": "update", "method": "PUT", "ref": ref, "payload": updated},
            {"operation": "get", "method": "GET", "ref": ref},
            {"operation": "list_search", "method": "GET", "params": {"tag": "workload"}},
            {"operation": "list_search", "method": "GET", "params": {"tag": "changed"}},
            {"operation": "delete", "method": "DELETE", "ref": ref},
            {"operation": "list_search", "method": "GET", "params": {"tag": "changed"}},
        ]
        trace.extend({"name": f"cycle_{i}_{j}_{s['operation']}", **s} for j, s in enumerate(steps))
    return trace
