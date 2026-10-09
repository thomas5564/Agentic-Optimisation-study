from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class NoteBase(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    body: Annotated[str, Field(min_length=1, max_length=5000)]
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for tag in value:
            normalized = str(tag).strip()
            if not normalized:
                continue
            if normalized not in seen:
                seen.add(normalized)
                cleaned.append(normalized)
        return sorted(cleaned)


class NoteCreate(NoteBase):
    pass


class NoteUpdate(NoteBase):
    pass


class Note(NoteBase):
    id: int

    model_config = {"populate_by_name": True}
