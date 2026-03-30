from __future__ import annotations

import enum
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class SkillSource(str, enum.Enum):
    professional = "professional"
    project = "project"
    internship = "internship"
    certification = "certification"
    education = "education"


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"
    __table_args__ = (
        CheckConstraint(
            "proficiency BETWEEN 1 AND 5", name="candidate_skills_proficiency_check"
        ),
        Index("idx_candidate_skills_candidate", "candidate_id"),
        Index("idx_candidate_skills_name", "skill_name"),
        Index("idx_candidate_skills_category", "skill_category"),
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    candidate_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_name: Mapped[str] = mapped_column(String(100), nullable=False)
    skill_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[SkillSource] = mapped_column(
        Enum(SkillSource, name="skill_source"), nullable=False
    )
    proficiency: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
