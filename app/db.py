from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from app.models import Note


def get_db_path() -> Path:
    configured = os.getenv("NOTES_DB_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent.parent / "notes.db"


def _connect() -> sqlite3.Connection:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_db() -> None:
    connection = _connect()
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    connection.commit()
    connection.close()


def _to_note(row: sqlite3.Row) -> Note:
    tags_value = row["tags"] or "[]"
    return Note(
        id=row["id"],
        title=row["title"],
        body=row["body"],
        tags=json.loads(tags_value),
    )


def create_note(title: str, body: str, tags: list[str]) -> Note:
    connection = _connect()
    payload = json.dumps(sorted({tag.strip() for tag in tags if tag and tag.strip()}))
    cursor = connection.execute(
        "INSERT INTO notes (title, body, tags) VALUES (?, ?, ?)",
        (title, body, payload),
    )
    note_id = cursor.lastrowid
    row = connection.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    connection.commit()
    connection.close()
    return _to_note(row)


def get_note(note_id: int) -> Note | None:
    connection = _connect()
    row = connection.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    connection.close()
    if row is None:
        return None
    return _to_note(row)


def list_notes(
    *,
    search_text: str | None = None,
    tags_filter: list[str] | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Note], int]:
    connection = _connect()
    rows = connection.execute("SELECT * FROM notes ORDER BY id ASC").fetchall()
    connection.close()

    notes = [_to_note(row) for row in rows]
    filtered = []
    for note in notes:
        matches_search = True
        if search_text is not None and search_text != "":
            matches_search = (search_text in note.title) or (search_text in note.body)

        matches_tags = True
        if tags_filter:
            tag_values = {tag.lower() for tag in tags_filter if tag}
            if not tag_values:
                matches_tags = True
            else:
                matches_tags = all(tag.lower() in {item.lower() for item in note.tags} for tag in tag_values)

        if matches_search and matches_tags:
            filtered.append(note)

    total = len(filtered)
    paginated = filtered[offset: offset + limit]
    return paginated, total


def update_note(note_id: int, title: str, body: str, tags: list[str]) -> Note | None:
    connection = _connect()
    row = connection.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if row is None:
        connection.close()
        return None
    payload = json.dumps(sorted({tag.strip() for tag in tags if tag and tag.strip()}))
    connection.execute(
        "UPDATE notes SET title = ?, body = ?, tags = ? WHERE id = ?",
        (title, body, payload, note_id),
    )
    updated = connection.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    connection.commit()
    connection.close()
    return _to_note(updated)


def delete_note(note_id: int) -> bool:
    connection = _connect()
    cursor = connection.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    connection.commit()
    connection.close()
    return cursor.rowcount > 0


def _storage_notes() -> list[dict[str, Any]]:
    connection = _connect()
    rows = connection.execute("SELECT * FROM notes ORDER BY id ASC").fetchall()
    connection.close()
    return [{"id": row["id"], "title": row["title"], "body": row["body"], "tags": json.loads(row["tags"])} for row in rows]
