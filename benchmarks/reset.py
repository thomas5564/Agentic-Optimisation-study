"""Seed a fresh candidate through its public API, preserving its schema/indexes."""
from benchmarks.fixtures import make_fixture
from benchmarks.oracle import Oracle


def reset_database(client, seed: int = 7, count: int = 20) -> Oracle:
    oracle = Oracle()
    empty = client.get("/notes")
    if not oracle.check({"method": "GET"}, empty.status_code, empty.json()):
        raise ValueError("Fixture setup requires a fresh, empty application database")
    for i, payload in enumerate(make_fixture(seed, count)):
        step = {"method": "POST", "bind": f"seed_{i}", "payload": payload}
        response = client.post("/notes", json=payload)
        if not oracle.check(step, response.status_code, response.json()):
            raise ValueError(f"Fixture response mismatch at note {i}")
    for offset in range(0, count, 100):
        step = {"method": "GET", "params": {"offset": offset, "limit": 100}}
        response = client.get("/notes", params=step["params"])
        if not oracle.check(step, response.status_code, response.json()):
            raise ValueError(f"Fixture list mismatch at offset {offset}")
    return oracle
