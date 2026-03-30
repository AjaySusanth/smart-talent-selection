from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class JobMatch(Base):
    __tablename__ = "job_matches"
    __table_args__ = (
        UniqueConstraint("jd_id", "candidate_id", name="uq_job_matches_jd_candidate"),
        Index("idx_job_matches_jd", "jd_id"),
        Index("idx_job_matches_final_score", "jd_id", "final_score"),
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    jd_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_descriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )

    semantic_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    rule_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    final_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)

    score_breakdown_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

    justification_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    justification_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ranked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
