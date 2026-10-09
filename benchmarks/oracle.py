"""Independent reference state. Never consult candidate models or storage helpers."""
from __future__ import annotations

from copy import deepcopy
import json


def normalize(payload: dict) -> dict:
    return {"title": payload["title"], "body": payload["body"],
            "tags": sorted({t.strip() for t in payload.get("tags", []) if t.strip()})}


def same_json(actual, expected) -> bool:
    # Serialization distinguishes booleans/floats from integer IDs/counts.
    return json.dumps(actual, sort_keys=True, ensure_ascii=False) == json.dumps(expected, sort_keys=True, ensure_ascii=False)


class Oracle:
    def __init__(self):
        self.notes: dict[int, dict] = {}
        self.refs: dict[str, int] = {}

    def path(self, step: dict) -> str:
        return f"/notes/{self.refs[step['ref']]}" if "ref" in step else "/notes"

    def check(self, step: dict, status: int, payload, content: bytes = b"") -> bool:
        method = step["method"]
        if method == "POST":
            if status != 201 or not isinstance(payload, dict):
                return False
            note_id = payload.get("id")
            if type(note_id) is not int or note_id in self.notes:
                return False
            expected = {"id": note_id, **normalize(step["payload"])}
            if not same_json(payload, expected):
                return False
            self.notes[note_id] = deepcopy(expected)
            self.refs[step["bind"]] = note_id
            return True
        if "ref" in step:
            note_id = self.refs[step["ref"]]
            if note_id not in self.notes:
                return status == 404 and same_json(payload, {"detail": "Note not found"})
            if method == "GET":
                return status == 200 and same_json(payload, self.notes[note_id])
            if method == "PUT":
                expected = {"id": note_id, **normalize(step["payload"])}
                if status != 200 or not same_json(payload, expected):
                    return False
                self.notes[note_id] = expected
                return True
            if method == "DELETE":
                if status != 204 or content:
                    return False
                del self.notes[note_id]
                return True
        params = step.get("params", {})
        q = params.get("q", "")
        tags = params.get("tag", [])
        tags = [tags] if isinstance(tags, str) else tags
        tags = [t.strip() for t in tags if t.strip()]
        selected = [n for _, n in sorted(self.notes.items())
                    if (q in n["title"] or q in n["body"]) and all(t in n["tags"] for t in tags)]
        offset, limit = params.get("offset", 0), params.get("limit", 20)
        expected = {"items": selected[offset:offset + limit], "total": len(selected), "offset": offset, "limit": limit}
        return status == 200 and same_json(payload, expected)
