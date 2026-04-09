"""Build structured embedding input text from CandidateProfile."""

from __future__ import annotations

from app.schemas.candidate_profile import CandidateProfile

_SOFT_SKILL_TERMS = {
    "problem solving",
    "leadership",
    "teamwork",
    "communication",
    "adaptability",
    "attention to detail",
    "time management",
    "collaboration",
    "critical thinking",
    "creativity",
    "work ethic",
}


def build_embedding_text(profile: CandidateProfile) -> str:
    """
    Construct recruiter-oriented embedding text from structured profile data.

    The output intentionally emphasizes technical capability signals while
    excluding generic soft-skill noise.
    """
    parts: list[str] = []

    if profile.normalised_skills:
        hard_skills = [
            skill.name
            for skill in profile.normalised_skills
            if skill.category != "soft_skill"
        ]
    else:
        hard_skills = [
            skill
            for skill in profile.skills
            if skill.strip().lower() not in _SOFT_SKILL_TERMS
        ]

    if hard_skills:
        parts.append(f"Skills: {', '.join(hard_skills)}")

    if profile.experience:
        exp_lines = [
            f"{exp.title} at {exp.company}"
            for exp in profile.experience
            if exp.title and exp.company
        ]
        if exp_lines:
            parts.append(f"Experience: {'; '.join(exp_lines)}")

    if profile.projects:
        proj_lines = [
            f"{project.name} using {', '.join(project.technologies)}"
            for project in profile.projects
            if project.name and project.technologies
        ]
        if proj_lines:
            parts.append(f"Projects: {'; '.join(proj_lines)}")

    if profile.education:
        latest = profile.education[0]
        if latest.degree and latest.field_of_study:
            parts.append(f"Education: {latest.degree} in {latest.field_of_study}")

    if profile.certifications:
        cert_names = [cert.name for cert in profile.certifications if cert.name]
        if cert_names:
            parts.append(f"Certifications: {', '.join(cert_names)}")

    return "\n\n".join(parts)
