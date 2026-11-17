"""Pydantic models for project notes (rich-text, document-sized)."""

from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.models.common import BluOnXBase

# Mirrors chk_project_notes_size in the database.
MAX_NOTE_HTML_CHARS = 2_000_000
MAX_NOTE_TEXT_CHARS = 1_000_000


def _clean_title(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Title is required")
    return cleaned


class ProjectNoteCreate(BluOnXBase):
    title: str = Field(max_length=255)
    content_html: str = Field(default="", max_length=MAX_NOTE_HTML_CHARS)
    content_text: str = Field(default="", max_length=MAX_NOTE_TEXT_CHARS)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _clean_title(value)


class ProjectNoteUpdate(BluOnXBase):
    title: str | None = Field(default=None, max_length=255)
    content_html: str | None = Field(default=None, max_length=MAX_NOTE_HTML_CHARS)
    content_text: str | None = Field(default=None, max_length=MAX_NOTE_TEXT_CHARS)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return _clean_title(value)


class ProjectNoteResponse(BluOnXBase):
    id: UUID
    project_id: UUID
    title: str
    content_html: str
    content_text: str
    created_by: UUID
    created_by_name: str | None = None
    updated_by: UUID | None = None
    updated_by_name: str | None = None
    created_at: datetime
    updated_at: datetime
    can_edit: bool = False
