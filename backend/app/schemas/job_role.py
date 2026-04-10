from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobRoleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None


class JobRoleUpdate(BaseModel):
    """Partial update for job role fields."""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None


class JobRoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    resume_count: int
