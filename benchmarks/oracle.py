from __future__ import annotations

from typing import Any


def validate_note_shape(note: dict[str, Any]) -> bool:
    return isinstance(note, dict) and {"id", "title", "body", "tags"}.issubset(note.keys())


def validate_list_response(
    response_json: dict[str, Any],
    expected_total: int,
    expected_titles: list[str] | None = None,
) -> bool:
    if not isinstance(response_json, dict):
        return False
    items = response_json.get("items")
    if not isinstance(items, list):
        return False
    total = response_json.get("total")
    if total != expected_total:
        return False
    if not all(validate_note_shape(item) for item in items):
        return False
    if expected_titles is not None:
        actual_titles = [item.get("title") for item in items]
        if actual_titles != expected_titles:
            return False
    return True


def validate_create_response(response_json: dict[str, Any], expected_title: str, expected_body: str) -> bool:
    if not validate_note_shape(response_json):
        return False
    return response_json.get("title") == expected_title and response_json.get("body") == expected_body


def validate_update_response(response_json: dict[str, Any], expected_title: str, expected_body: str) -> bool:
    return validate_create_response(response_json, expected_title, expected_body)
