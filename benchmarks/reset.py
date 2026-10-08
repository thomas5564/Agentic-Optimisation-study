from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.db import get_db_path, initialize_db
from app.seed import seed_database


def reset_database(seed: int = 7, count: int = 20) -> list[dict[str, Any]]:
    """Reset the notes DB and restore a deterministic fixture.

    The same seed and count must produce the same logical dataset across runs.
    """
    db_path = get_db_path()
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("DROP TABLE IF EXISTS notes")
        connection.commit()
        initialize_db()
        expected = seed_database(seed, count)
        for note in expected:
            connection.execute(
                "INSERT INTO notes (id, title, body, tags) VALUES (?, ?, ?, ?)",
                (int(note["id"]), str(note["title"]), str(note["body"]), json.dumps(note["tags"])),
            )
        connection.commit()
    finally:
        connection.close()
    return expected
