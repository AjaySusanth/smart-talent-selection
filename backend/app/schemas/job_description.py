from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JDRequirements(BaseModel):
    mandatory_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    min_experience_years: float = Field(default=0.0, ge=0)
    certifications: list[str] = Field(default_factory=list)

    @field_validator(
        "mandatory_skills", "preferred_skills", "certifications", mode="before"
    )
    @classmethod
    def _normalise_string_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            return []

        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            raw = str(item).strip()
            if not raw:
                continue
            key = raw.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(raw)
        return cleaned


class JobDescriptionCreate(BaseModel):
    job_role_id: UUID
    raw_text: str = Field(min_length=20, max_length=10000)


class JobDescriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_role_id: UUID
    raw_text: str
    requirements: JDRequirements
    is_active: bool
    created_at: datetime
    status: str


class CandidateRankingBreakdown(BaseModel):
    semantic_score: float
    rule_score: float
    final_score: float

    skill_score: float
    exp_score: float
    projects_score: float
    professional_score: float
    certs_score: float

    matching_mandatory_skills: int
    total_mandatory_skills: int


class CandidateRankingResult(BaseModel):
    candidate_id: UUID
    resume_upload_id: UUID
    total_exp_years: float
    breakdown: CandidateRankingBreakdown
    justification_text: str | None = None


class JobDescriptionRankingResponse(BaseModel):
    jd_id: UUID
    total_candidates: int
    returned_candidates: int
    candidates: list[CandidateRankingResult]
