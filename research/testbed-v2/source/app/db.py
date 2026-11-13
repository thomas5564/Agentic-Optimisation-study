from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from app.models import Note

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        tags TEXT NOT NULL DEFAULT '[]'
    )
    """,
)


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
    connection.execute("PRAGMA case_sensitive_like = ON")
    for statement in SCHEMA:
        connection.execute(statement)
    connection.commit()
    return connection


def _release(connection: sqlite3.Connection) -> None:
    connection.close()


def initialize_db() -> None:
    _release(_connect())


def _normalize_tags(tags: list[str]) -> str:
    return json.dumps(sorted({tag.strip() for tag in tags if tag and tag.strip()}))


def _make_note(note_id: int, title: str, body: str, tags: str) -> Note:
    return Note.model_validate({"id": note_id, "title": title, "body": body, "tags": json.loads(tags or "[]")})


def _to_note(row: sqlite3.Row) -> Note:
    return _make_note(row["id"], row["title"], row["body"], row["tags"])

def create_note(title: str, body: str, tags: list[str]) -> Note:
    connection = _connect()
    payload = _normalize_tags(tags)
    cursor = connection.execute(
        "INSERT INTO notes (title, body, tags) VALUES (?, ?, ?)",
        (title, body, payload),
    )
    note_id = cursor.lastrowid
    connection.commit()
    created = None
    for row in connection.execute("SELECT id, title, body, tags FROM notes").fetchall():
        note = _to_note(row)
        if note.id == note_id:
            created = note
    _release(connection)
    return created


def get_note(note_id: int) -> Note | None:
    connection = _connect()
    rows = connection.execute("SELECT id, title, body, tags FROM notes ORDER BY id ASC").fetchall()
    _release(connection)
    notes = [_to_note(row) for row in rows]
    for note in notes:
        if note.id == note_id:
            return note
    return None


def list_notes(
    *,
    search_text: str | None = None,
    tags_filter: list[str] | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Note], int]:
    wanted = [tag for tag in tags_filter or [] if tag]
    connection = _connect()
    rows = connection.execute("SELECT id, title, body, tags FROM notes ORDER BY id ASC").fetchall()
    _release(connection)
    matches = []
    for note in map(_to_note, rows):
        if search_text and search_text not in note.title and search_text not in note.body:
            continue
        if all(tag in note.tags for tag in wanted):
            matches.append(note)
    return matches[offset: offset + limit], len(matches)


def update_note(note_id: int, title: str, body: str, tags: list[str]) -> Note | None:
    connection = _connect()
    existing = {note.id: note for note in map(_to_note, connection.execute("SELECT id, title, body, tags FROM notes"))}
    if note_id not in existing:
        _release(connection)
        return None
    payload = _normalize_tags(tags)
    connection.execute(
        "UPDATE notes SET title = ?, body = ?, tags = ? WHERE id = ?",
        (title, body, payload, note_id),
    )
    connection.commit()
    updated = {note.id: note for note in map(_to_note, connection.execute("SELECT id, title, body, tags FROM notes"))}
    _release(connection)
    return updated[note_id]


def delete_note(note_id: int) -> bool:
    connection = _connect()
    ids = [_to_note(row).id for row in connection.execute("SELECT id, title, body, tags FROM notes").fetchall()]
    if note_id not in ids:
        _release(connection)
        return False
    connection.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    connection.commit()
    connection.execute("VACUUM")
    _release(connection)
    return True
