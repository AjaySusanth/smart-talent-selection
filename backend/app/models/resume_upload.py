from __future__ import annotations

import enum
from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class UploadStatus(str, enum.Enum):
    uploaded = "uploaded"
    queued = "queued"
    parsing = "parsing"
    parsed = "parsed"
    failed = "failed"


class ResumeUpload(Base):
    __tablename__ = "resume_uploads"
    __table_args__ = (
        Index("idx_resume_uploads_job_role", "job_role_id"),
        Index("idx_resume_uploads_status", "status"),
        Index("idx_resume_uploads_batch", "batch_date"),
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    job_role_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_key: Mapped[str] = mapped_column(String(500), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus, name="upload_status"),
        nullable=False,
        default=UploadStatus.uploaded,
        server_default="uploaded",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    batch_date: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
