from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.models.candidate import Candidate
from app.models.candidate_experience import CandidateExperience, ExperienceType
from app.models.candidate_skill import CandidateSkill, SkillSource
from app.models.job_description import JobDescription
from app.models.job_match import JobMatch
from app.models.job_role import JobRole
from app.models.job_scoring_config import JobScoringConfig
from app.models.resume_upload import ResumeUpload, UploadStatus

__all__ = [
    "Base",
    "Candidate",
    "CandidateExperience",
    "CandidateSkill",
    "ExperienceType",
    "JobDescription",
    "JobMatch",
    "JobRole",
    "JobScoringConfig",
    "ResumeUpload",
    "SkillSource",
    "UploadStatus",
]
