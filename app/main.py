from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db import create_note, delete_note, get_note, initialize_db, list_notes, update_note
from app.models import Note, NoteCreate, NoteUpdate

app = FastAPI(title="Notes API")
initialize_db()
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")


@app.on_event("startup")
async def startup_event() -> None:
    initialize_db()


@app.post("/notes", response_model=Note, status_code=status.HTTP_201_CREATED)
def create_note_endpoint(note: NoteCreate) -> Note:
    return create_note(note.title, note.body, note.tags)


@app.get("/notes/{note_id}", response_model=Note)
def read_note(note_id: int) -> Note:
    note = get_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@app.get("/notes")
def list_notes_endpoint(
    q: str | None = Query(default=None, description="Substring search over title or body."),
    tag: list[str] = Query(default_factory=list),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    clean_tags = [item.strip() for item in tag if isinstance(item, str) and item.strip()]
    items, total = list_notes(search_text=q, tags_filter=clean_tags, offset=offset, limit=limit)
    return {
        "items": [note.model_dump() for note in items],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@app.put("/notes/{note_id}", response_model=Note)
def update_note_endpoint(note_id: int, note: NoteUpdate) -> Note:
    updated = update_note(note_id, note.title, note.body, note.tags)
    if updated is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return updated


@app.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note_endpoint(note_id: int) -> Response:
    deleted = delete_note(note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Note not found")
    return Response(status_code=204)


@app.get("/", include_in_schema=False)
def read_index() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent / "static" / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
