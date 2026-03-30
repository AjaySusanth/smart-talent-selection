from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class JobScoringConfig(Base):
    __tablename__ = "job_scoring_config"
    __table_args__ = (
        CheckConstraint(
            "skill_match_weight + exp_years_weight + projects_weight + prof_exp_weight + certs_weight = 100",
            name="weights_sum_100",
        ),
        CheckConstraint(
            "skill_match_weight BETWEEN 0 AND 100", name="skill_match_range"
        ),
        CheckConstraint("exp_years_weight BETWEEN 0 AND 100", name="exp_years_range"),
        CheckConstraint("projects_weight BETWEEN 0 AND 100", name="projects_range"),
        CheckConstraint("prof_exp_weight BETWEEN 0 AND 100", name="prof_exp_range"),
        CheckConstraint("certs_weight BETWEEN 0 AND 100", name="certs_range"),
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
        unique=True,
    )
    preset_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="Default", server_default="Default"
    )

    skill_match_weight: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=40, server_default=text("40")
    )
    exp_years_weight: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=20, server_default=text("20")
    )
    projects_weight: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=20, server_default=text("20")
    )
    prof_exp_weight: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=15, server_default=text("15")
    )
    certs_weight: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=5, server_default=text("5")
    )

    is_customised: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
