"""
Pydantic schemas for the structured candidate profile.

These schemas define the exact JSON structure that Gemini must produce
when extracting information from resume text. They also serve as the
validation layer before data is stored in the candidates.profile_json
JSONB column.

The schema is intentionally flat and explicit so the LLM can follow it reliably.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Education(BaseModel):
    """A single educational qualification."""

    institution: str = Field(description="Name of the university or school")
    degree: str = Field(description="Degree type, e.g. 'B.Tech', 'MBA', 'High School Diploma'")
    field_of_study: str | None = Field(
        default=None, description="Major or specialisation, e.g. 'Computer Science'"
    )
    start_date: str | None = Field(
        default=None, description="Start date in 'YYYY-MM' or 'YYYY' format"
    )
    end_date: str | None = Field(
        default=None,
        description="End date in 'YYYY-MM' or 'YYYY' format. Use 'Present' if currently enrolled",
    )
    gpa: str | None = Field(default=None, description="GPA or percentage if mentioned")


class Experience(BaseModel):
    """A single work experience entry."""

    company: str = Field(description="Company or organisation name")
    title: str = Field(description="Job title or role")
    location: str | None = Field(default=None, description="City, State, or 'Remote'")
    start_date: str | None = Field(
        default=None, description="Start date in 'YYYY-MM' or 'YYYY' format"
    )
    end_date: str | None = Field(
        default=None,
        description="End date in 'YYYY-MM' or 'YYYY' format. Use 'Present' if current",
    )
    responsibilities: list[str] = Field(
        default_factory=list,
        description="Key responsibilities or achievements as bullet points",
    )


class Certification(BaseModel):
    """A professional certification or course."""

    name: str = Field(description="Certification or course name")
    issuer: str | None = Field(default=None, description="Issuing organisation")
    date: str | None = Field(default=None, description="Date obtained in 'YYYY-MM' or 'YYYY' format")


class Project(BaseModel):
    """A notable project from the resume."""

    name: str = Field(description="Project name or title")
    description: str | None = Field(default=None, description="Brief description of the project")
    technologies: list[str] = Field(
        default_factory=list, description="Technologies/tools used"
    )
    url: str | None = Field(default=None, description="Deployed site / demo URL if mentioned")
    github_url: str | None = Field(default=None, description="GitHub repository URL if mentioned")


class NormalisedSkill(BaseModel):
    """Canonical skill entry used by downstream matching and scoring."""

    name: str = Field(description="Canonical skill name")
    category: Literal[
        "language", "framework", "database", "tool", "cloud", "soft_skill", "stack"
    ] = Field(description="Skill category")


class CandidateProfile(BaseModel):
    """
    The complete structured profile extracted from a resume.

    Stored in candidates.profile_json (JSONB).
    Produced by Gemini 2.5 Flash (Task 3.4).
    """

    full_name: str = Field(description="Candidate's full name")
    email: str | None = Field(default=None, description="Primary email address")
    phone: str | None = Field(default=None, description="Primary phone number")
    location: str | None = Field(default=None, description="City, State, Country")
    linkedin_url: str | None = Field(default=None, description="LinkedIn profile URL")
    github_url: str | None = Field(default=None, description="GitHub profile URL")
    portfolio_url: str | None = Field(default=None, description="Personal website or portfolio URL")

    summary: str = Field(
        description=(
            "Professional summary or objective. "
            "If not present, generate a 2-3 sentence summary from the resume content"
        )
    )

    skills: list[str] = Field(
        default_factory=list,
        description="All technical and soft skills mentioned, each as a separate item",
    )
    normalised_skills: list[NormalisedSkill] = Field(
        default_factory=list,
        description="Deduplicated canonical skills with categories",
    )
    languages: list[str] = Field(
        default_factory=list,
        description="Spoken/written languages with proficiency if mentioned",
    )

    experience: list[Experience] = Field(
        default_factory=list,
        description="Work experience entries, ordered most recent first",
    )
    education: list[Education] = Field(
        default_factory=list,
        description="Educational qualifications, ordered most recent first",
    )
    certifications: list[Certification] = Field(
        default_factory=list,
        description="Professional certifications and courses",
    )
    projects: list[Project] = Field(
        default_factory=list,
        description="Notable projects mentioned in the resume",
    )

    total_experience_years: float = Field(
        default=0.0,
        description=(
            "Total years of professional work experience, "
            "calculated by summing all experience entry durations"
        ),
    )
