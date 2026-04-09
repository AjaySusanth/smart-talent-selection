"""Persistence service for parsed candidate profiles and embeddings.

Writes three table groups in a single transaction:
  1. candidates        — the main profile row with embedding
  2. candidate_skills  — flat normalised skills for rule-based scoring
  3. candidate_experience — experience + project entries for scoring

All inserts are atomic: if any fails, everything rolls back.
"""

from __future__ import annotations

import re
from datetime import date

import structlog
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.candidate_experience import CandidateExperience, ExperienceType
from app.models.candidate_skill import CandidateSkill, SkillSource
from app.models.resume_upload import ResumeUpload, UploadStatus
from app.schemas.candidate_profile import CandidateProfile, Experience, Project

logger = structlog.get_logger(__name__)

_EXPECTED_SECTIONS_COUNT = 5
_LOW_CONFIDENCE_THRESHOLD = 0.30

# Title keywords that indicate an internship rather than professional role
_INTERN_KEYWORDS = re.compile(
    r"\b(intern|internship|trainee|apprentice|co-?op)\b", re.IGNORECASE
)


# ─── Helpers ──────────────────────────────────────────────────────────────


def _is_low_confidence(profile: CandidateProfile) -> bool:
    """Flag profile as low confidence if more than 30% core sections are empty."""
    empty_sections = sum(
        [
            not profile.skills,
            not profile.experience,
            not profile.education,
            not profile.projects,
            not profile.certifications,
        ]
    )
    return (empty_sections / _EXPECTED_SECTIONS_COUNT) > _LOW_CONFIDENCE_THRESHOLD


def _parse_date(date_str: str | None, is_end: bool = False) -> date | None:
    """Parse 'YYYY-MM', 'YYYY', or 'Present' into a date object."""
    if not date_str or not isinstance(date_str, str):
        return None

    clean = date_str.strip().lower()
    if clean == "present":
        return date.today()

    m_ym = re.match(r"^(\d{4})-(\d{1,2})$", clean)
    if m_ym:
        return date(int(m_ym.group(1)), int(m_ym.group(2)), 1)

    m_y = re.match(r"^(\d{4})$", clean)
    if m_y:
        y = int(m_y.group(1))
        return date(y, 12, 31) if is_end else date(y, 1, 1)

    return None


def _duration_months(start: date | None, end: date | None) -> int | None:
    """Compute month difference; returns None if either date is missing."""
    if not start or not end or end < start:
        return None
    return (end.year - start.year) * 12 + (end.month - start.month)


def _infer_exp_type(title: str | None) -> ExperienceType:
    """Classify experience as internship if the title matches intern keywords."""
    if title and _INTERN_KEYWORDS.search(title):
        return ExperienceType.internship
    return ExperienceType.professional


# ─── Skill row builders ──────────────────────────────────────────────────


def _build_skill_rows(
    candidate_id, profile: CandidateProfile
) -> list[CandidateSkill]:
    """Create CandidateSkill ORM objects with intelligent source attribution."""
    if not profile.normalised_skills:
        return []

    # 1. Map skill names to their appearance in various sections
    project_skills: set[str] = set()
    for p in profile.projects or []:
        for t in p.technologies or []:
            project_skills.add(t.strip().lower())

    cert_skills: set[str] = set()
    for c in profile.certifications or []:
        cert_skills.add(c.name.strip().lower())

    edu_skills: set[str] = set()
    for e in profile.education or []:
        if e.field_of_study:
            edu_skills.add(e.field_of_study.strip().lower())

    rows: list[CandidateSkill] = []
    seen: set[str] = set()

    # If there is no professional experience, default to project
    has_pro_exp = len(profile.experience) > 0 or profile.total_experience_years > 0.5

    for skill in profile.normalised_skills:
        name_lower = skill.name.strip().lower()
        if name_lower in seen:
            continue
        seen.add(name_lower)

        # 2. Determine the most likely source
        # Order of attribution: Professional > Project > Certification > Education
        if has_pro_exp:
            source = SkillSource.professional
        elif name_lower in project_skills:
            source = SkillSource.project
        elif name_lower in cert_skills:
            source = SkillSource.certification
        elif any(name_lower in c_name for c_name in cert_skills):
            source = SkillSource.certification
        elif any(name_lower in e_name for e_name in edu_skills):
            source = SkillSource.education
        else:
            # Fallback for students with no experience: treat standalone skills as project-based
            source = SkillSource.project if not has_pro_exp else SkillSource.professional

        rows.append(
            CandidateSkill(
                candidate_id=candidate_id,
                skill_name=skill.name,
                skill_category=skill.category,
                source=source,
            )
        )

    return rows


# ─── Experience row builders ─────────────────────────────────────────────


def _build_experience_rows(
    candidate_id, profile: CandidateProfile
) -> list[CandidateExperience]:
    """Create CandidateExperience ORM objects from experience + project entries."""
    rows: list[CandidateExperience] = []

    # Work experience entries
    for exp in profile.experience or []:
        start = _parse_date(exp.start_date)
        end = _parse_date(exp.end_date, is_end=True)
        is_current = (
            exp.end_date is not None
            and exp.end_date.strip().lower() == "present"
        )

        rows.append(
            CandidateExperience(
                candidate_id=candidate_id,
                exp_type=_infer_exp_type(exp.title),
                company=exp.company,
                role=exp.title,
                description=(
                    "\n".join(exp.responsibilities)
                    if exp.responsibilities
                    else None
                ),
                start_date=start,
                end_date=end if not is_current else None,
                is_current=is_current,
                duration_months=_duration_months(start, end),
            )
        )

    # Project entries → stored as exp_type=project
    for proj in profile.projects or []:
        rows.append(
            CandidateExperience(
                candidate_id=candidate_id,
                exp_type=ExperienceType.project,
                company=None,
                role=proj.name,
                description=proj.description,
                start_date=None,
                end_date=None,
                is_current=False,
                duration_months=None,
            )
        )

    return rows


# ─── Main persistence function ────────────────────────────────────────────


def persist_candidate(
    session: Session,
    resume_upload_id: str,
    raw_text: str,
    profile: CandidateProfile,
    embedding_text: str,
    embedding_vector: list[float],
) -> Candidate:
    """Persist candidate row, skills, experience, and mark upload parsed.

    All writes happen in a single transaction — if any insert fails,
    nothing is committed.
    """
    low_confidence = _is_low_confidence(profile)

    candidate = Candidate(
        resume_upload_id=resume_upload_id,
        raw_text=raw_text,
        profile_json=profile.model_dump(mode="json"),
        summary_text=embedding_text,
        embedding=embedding_vector,
        total_exp_years=profile.total_experience_years or 0.0,
        is_low_confidence=low_confidence,
    )

    try:
        # 1. Insert candidate row (need to flush to get the generated id)
        session.add(candidate)
        session.flush()

        # 2. Insert flat skill rows
        skill_rows = _build_skill_rows(candidate.id, profile)
        if skill_rows:
            session.add_all(skill_rows)

        # 3. Insert experience + project rows
        exp_rows = _build_experience_rows(candidate.id, profile)
        if exp_rows:
            session.add_all(exp_rows)

        # 4. Mark upload as parsed
        session.execute(
            update(ResumeUpload)
            .where(ResumeUpload.id == resume_upload_id)
            .values(status=UploadStatus.parsed, error_message=None)
        )

        session.commit()
        session.refresh(candidate)
    except Exception:
        session.rollback()
        raise

    logger.info(
        "candidate_persisted",
        candidate_id=str(candidate.id),
        resume_upload_id=resume_upload_id,
        total_exp_years=float(candidate.total_exp_years),
        is_low_confidence=low_confidence,
        embedding_dims=len(embedding_vector),
        skill_rows=len(skill_rows),
        experience_rows=len(exp_rows),
    )

    return candidate
