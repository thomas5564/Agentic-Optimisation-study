"""Runner-owned fixture generation, independent of candidate application code."""
from __future__ import annotations

import random


def make_fixture(seed: int, count: int) -> list[dict]:
    rng = random.Random(seed)
    tags = ["research", "notes", "alpha", "beta", "gamma", "work", "personal"]
    return [
        {
            "title": f"{['Alpha', 'Beta', 'Gamma', 'Delta', 'Echo'][i % 5]} #{i}",
            "body": f"Deterministic note {i}. Unicode: café 世界. seed={seed}",
            "tags": sorted({rng.choice(tags) for _ in range(2)}),
        }
        for i in range(1, count + 1)
    ]
