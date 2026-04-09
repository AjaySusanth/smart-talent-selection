from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScoringConfigBase(BaseModel):
    skill_match_weight: int = Field(default=40, ge=0, le=100)
    exp_years_weight: int = Field(default=20, ge=0, le=100)
    projects_weight: int = Field(default=20, ge=0, le=100)
    prof_exp_weight: int = Field(default=15, ge=0, le=100)
    certs_weight: int = Field(default=5, ge=0, le=100)

    @model_validator(mode="after")
    def validate_weights_sum(self) -> ScoringConfigBase:
        total = (
            self.skill_match_weight
            + self.exp_years_weight
            + self.projects_weight
            + self.prof_exp_weight
            + self.certs_weight
        )
        if total != 100:
            raise ValueError(f"Weights must sum to exactly 100, got {total}")
        return self


class ScoringConfigUpdate(ScoringConfigBase):
    pass


class ScoringConfigResponse(ScoringConfigBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_role_id: UUID
    preset_name: str
    is_customised: bool
    updated_at: datetime
    updated_by: str | None
