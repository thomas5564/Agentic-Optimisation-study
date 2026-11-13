from __future__ import annotations

import random


def seed_database(seed: int, count: int) -> list[dict[str, object]]:
    rng = random.Random(seed)
    prefixes = ["Alpha", "Beta", "Gamma", "Delta", "Echo"]
    bodies = [
        "Baseline note body for deterministic seeding.",
        "A second note used to validate stable outputs.",
        "This note is intentionally repeatable across runs.",
        "Seed data for API testing and persistence checks.",
    ]
    tag_pool = ["research", "notes", "alpha", "beta", "gamma", "work", "personal"]

    notes: list[dict[str, object]] = []
    for index in range(1, count + 1):
        title = f"{prefixes[index % len(prefixes)]} #{index}"
        body = f"{bodies[index % len(bodies)]} seed={seed}"
        tags = sorted({rng.choice(tag_pool) for _ in range(2)})
        notes.append({
            "id": index,
            "title": title,
            "body": body,
            "tags": tags,
        })
    return notes
