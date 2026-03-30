"""
Shared base schemas, types, and mixins for all Pydantic models.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BluOnXBase(BaseModel):
    """Base for all schemas. Enables from_attributes for ORM-like dicts."""

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    """Generic message response."""

    detail: str


class SignedUrlResponse(BaseModel):
    """Response containing a signed download URL."""

    url: str
