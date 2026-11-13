"""Researcher-only generator for testbed v2: baseline, reference and ablation variants.

Only app/db.py differs from the original frozen baseline. Each fix has exactly one naive form
(baseline) and one optimized form (reference), so any subset of fixes is a valid, comparable app.
This file contains the solutions; it is never placed in an agent workspace.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from controller.storage import load_baseline

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "research" / "baseline"

FIXES = {
    "connection": ("cache", "Reuse a per-thread connection; create the schema once instead of on every call"),
    "get_lookup": ("query", "Fetch one note by primary key instead of scanning every note"),
    "list_sql": ("query", "Filter, count and paginate in SQL instead of in Python"),
    "tag_index": ("index", "Indexed tag table for tag filters (builds on list_sql)"),
    "write_create": ("query", "create_note: use lastrowid instead of rescanning all notes"),
    "write_update": ("query", "update_note: use rowcount instead of rescanning all notes before and after"),
    "write_delete": ("query", "delete_note: use rowcount instead of rescanning all notes"),
    "no_vacuum": ("other", "Do not VACUUM the database after every delete"),
    "construct": ("serialization", "Build notes from trusted stored rows without re-validating them"),
}
REQUIRES = {"tag_index": "list_sql"}


def render_db(fixes: set[str]) -> str:
    unknown = fixes - FIXES.keys()
    if unknown:
        raise ValueError(f"Unknown fixes: {sorted(unknown)}")
    for fix, needed in REQUIRES.items():
        if fix in fixes and needed not in fixes:
            raise ValueError(f"{fix} requires {needed}")
    on = fixes.__contains__
    tag_ddl = ('''
    """
    CREATE TABLE IF NOT EXISTS note_tags (
        note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
        tag TEXT NOT NULL,
        PRIMARY KEY (tag, note_id)
    ) WITHOUT ROWID
    """,
    "CREATE INDEX IF NOT EXISTS note_tags_note ON note_tags (note_id)",''' if on("tag_index") else "")
    parts = ['''from __future__ import annotations

import json
import os
import sqlite3
''' + ("import threading\n" if on("connection") else "") + '''from pathlib import Path

from app.models import Note

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        tags TEXT NOT NULL DEFAULT '[]'
    )
    """,''' + tag_ddl + '''
)


def get_db_path() -> Path:
    configured = os.getenv("NOTES_DB_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent.parent / "notes.db"


''']
    if on("connection"):
        parts.append('''_local = threading.local()


def _connect() -> sqlite3.Connection:
    path = get_db_path()
    cache = getattr(_local, "connections", None)
    if cache is None:
        cache = _local.connections = {}
    connection = cache.get(path)
    if connection is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA case_sensitive_like = ON")
        for statement in SCHEMA:
            connection.execute(statement)
        connection.commit()
        cache[path] = connection
    return connection


def _release(connection: sqlite3.Connection) -> None:
    pass
''')
    else:
        parts.append('''def _connect() -> sqlite3.Connection:
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
''')
    parts.append('''

def initialize_db() -> None:
    _release(_connect())


def _normalize_tags(tags: list[str]) -> str:
    return json.dumps(sorted({tag.strip() for tag in tags if tag and tag.strip()}))


''')
    if on("construct"):
        parts.append('''def _make_note(note_id: int, title: str, body: str, tags: str) -> Note:
    return Note.model_construct(id=note_id, title=title, body=body, tags=json.loads(tags))
''')
    else:
        parts.append('''def _make_note(note_id: int, title: str, body: str, tags: str) -> Note:
    return Note.model_validate({"id": note_id, "title": title, "body": body, "tags": json.loads(tags or "[]")})
''')
    parts.append('''

def _to_note(row: sqlite3.Row) -> Note:
    return _make_note(row["id"], row["title"], row["body"], row["tags"])
''')
    tag_rows = ('''    connection.executemany(
        "INSERT INTO note_tags (note_id, tag) VALUES (?, ?)",
        [(note_id, tag) for tag in json.loads(payload)],
    )
''' if on("tag_index") else "")
    retag = ('''    connection.execute("DELETE FROM note_tags WHERE note_id = ?", (note_id,))
''' + tag_rows) if on("tag_index") else ""
    if on("write_create"):
        parts.append('''
def create_note(title: str, body: str, tags: list[str]) -> Note:
    connection = _connect()
    payload = _normalize_tags(tags)
    cursor = connection.execute(
        "INSERT INTO notes (title, body, tags) VALUES (?, ?, ?)",
        (title, body, payload),
    )
    note_id = cursor.lastrowid
''' + tag_rows + '''    connection.commit()
    _release(connection)
    return _make_note(note_id, title, body, payload)

''')
    else:
        parts.append('''
def create_note(title: str, body: str, tags: list[str]) -> Note:
    connection = _connect()
    payload = _normalize_tags(tags)
    cursor = connection.execute(
        "INSERT INTO notes (title, body, tags) VALUES (?, ?, ?)",
        (title, body, payload),
    )
    note_id = cursor.lastrowid
''' + tag_rows + '''    connection.commit()
    created = None
    for row in connection.execute("SELECT id, title, body, tags FROM notes").fetchall():
        note = _to_note(row)
        if note.id == note_id:
            created = note
    _release(connection)
    return created

''')
    if on("get_lookup"):
        parts.append('''
def get_note(note_id: int) -> Note | None:
    connection = _connect()
    row = connection.execute("SELECT id, title, body, tags FROM notes WHERE id = ?", (note_id,)).fetchone()
    _release(connection)
    if row is None:
        return None
    return _to_note(row)

''')
    else:
        parts.append('''
def get_note(note_id: int) -> Note | None:
    connection = _connect()
    rows = connection.execute("SELECT id, title, body, tags FROM notes ORDER BY id ASC").fetchall()
    _release(connection)
    notes = [_to_note(row) for row in rows]
    for note in notes:
        if note.id == note_id:
            return note
    return None

''')
    if on("list_sql"):
        tag_clause = ('"notes.id IN (SELECT note_id FROM note_tags WHERE tag = ?)"' if on("tag_index")
                      else '"EXISTS (SELECT 1 FROM json_each(notes.tags) WHERE json_each.value = ?)"')
        parts.append('''
def list_notes(
    *,
    search_text: str | None = None,
    tags_filter: list[str] | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Note], int]:
    clauses: list[str] = []
    params: list[object] = []
    if search_text:
        clauses.append("(instr(title, ?) > 0 OR instr(body, ?) > 0)")
        params += [search_text, search_text]
    for tag in dict.fromkeys(tag for tag in tags_filter or [] if tag):
        clauses.append(''' + tag_clause + ''')
        params.append(tag)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    connection = _connect()
    total = connection.execute(f"SELECT COUNT(*) FROM notes{where}", params).fetchone()[0]
    rows = connection.execute(
        f"SELECT id, title, body, tags FROM notes{where} ORDER BY id ASC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    _release(connection)
    return [_to_note(row) for row in rows], total

''')
    else:
        parts.append('''
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

''')
    if on("write_update"):
        parts.append('''
def update_note(note_id: int, title: str, body: str, tags: list[str]) -> Note | None:
    connection = _connect()
    payload = _normalize_tags(tags)
    cursor = connection.execute(
        "UPDATE notes SET title = ?, body = ?, tags = ? WHERE id = ?",
        (title, body, payload, note_id),
    )
    if cursor.rowcount == 0:
        connection.rollback()
        _release(connection)
        return None
''' + retag + '''    connection.commit()
    _release(connection)
    return _make_note(note_id, title, body, payload)

''')
    else:
        parts.append('''
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
''' + retag + '''    connection.commit()
    updated = {note.id: note for note in map(_to_note, connection.execute("SELECT id, title, body, tags FROM notes"))}
    _release(connection)
    return updated[note_id]

''')
    vacuum = "" if on("no_vacuum") else '    connection.execute("VACUUM")\n'
    if on("write_delete"):
        parts.append('''
def delete_note(note_id: int) -> bool:
    connection = _connect()
    cursor = connection.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    connection.commit()
    deleted = cursor.rowcount > 0
''' + ('    if deleted:\n        connection.execute("VACUUM")\n' if vacuum else "") + '''    _release(connection)
    return deleted
''')
    else:
        parts.append('''
def delete_note(note_id: int) -> bool:
    connection = _connect()
    ids = [_to_note(row).id for row in connection.execute("SELECT id, title, body, tags FROM notes").fetchall()]
    if note_id not in ids:
        _release(connection)
        return False
    connection.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    connection.commit()
''' + vacuum + '''    _release(connection)
    return True
''')
    return "".join(parts)


def variant_files(fixes: set[str]) -> dict[str, str]:
    files = load_baseline(ORIGINAL)
    files["app/db.py"] = render_db(fixes)
    return files


def write_variant(destination: Path, fixes: set[str], lock: bool = False) -> None:
    for name, text in variant_files(fixes).items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    if lock:
        (destination / "requirements.lock").write_text((ROOT / "requirements.lock").read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixes", default="", help="Comma-separated fixes; 'all' for the reference")
    parser.add_argument("--with-lock", action="store_true", help="Also copy requirements.lock (needed to freeze)")
    args = parser.parse_args()
    fixes = set(FIXES) if args.fixes == "all" else {f for f in args.fixes.split(",") if f}
    write_variant(args.output, fixes, args.with_lock)


if __name__ == "__main__":
    main()
