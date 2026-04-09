from __future__ import annotations

import json

import structlog
from groq import Groq

from app.core.config import settings
from app.schemas.job_description import JDRequirements
from app.services.parsing.embedding_generator import generate_embedding
from app.services.parsing.skill_normaliser import normalise_skills

logger = structlog.get_logger(__name__)

_MODEL_NAME = "llama-3.3-70b-versatile"
_client = Groq(api_key=settings.groq_api_key)

_SYSTEM_PROMPT = """You extract job description requirements into strict JSON.
Rules:
1. Return only JSON; no markdown.
2. mandatory_skills: list of hard requirements only.
3. preferred_skills: list of nice-to-have skills.
4. certifications: credential names only.
5. Parse years phrases like '3+ years', 'minimum 3 years', 'at least 3 years' into min_experience_years = 3.0.
6. If years are missing, use 0.
7. Never invent requirements that are not present.

Output schema:
{
  "mandatory_skills": ["string"],
  "preferred_skills": ["string"],
  "min_experience_years": 0.0,
  "certifications": ["string"]
}
"""


def _coerce_requirements(payload: dict) -> JDRequirements:
    if not isinstance(payload, dict):
        raise ValueError("JD extractor returned a non-object payload")

    # Backward compatibility for alternate key names
    payload = dict(payload)
    if "mandatory_skills" not in payload:
        payload["mandatory_skills"] = payload.get("required_skills", [])
    if "min_experience_years" not in payload:
        payload["min_experience_years"] = payload.get("min_years_experience", 0)

    requirements = JDRequirements.model_validate(payload)

    # Normalise JD skills with the same pipeline used for candidate skills.
    mandatory = normalise_skills(requirements.mandatory_skills)
    preferred = normalise_skills(requirements.preferred_skills)

    return JDRequirements(
        mandatory_skills=[skill.name for skill in mandatory],
        preferred_skills=[skill.name for skill in preferred],
        min_experience_years=requirements.min_experience_years,
        certifications=requirements.certifications,
    )


def extract_requirements(text: str) -> JDRequirements:
    if not text or not text.strip():
        raise ValueError("Cannot extract requirements from empty JD text")

    response = _client.chat.completions.create(
        model=_MODEL_NAME,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=1200,
    )

    content = response.choices[0].message.content if response.choices else None
    if not content:
        raise ValueError("JD extractor returned an empty response")

    payload = json.loads(content)
    requirements = _coerce_requirements(payload)

    logger.info(
        "jd_requirements_extracted",
        mandatory_count=len(requirements.mandatory_skills),
        preferred_count=len(requirements.preferred_skills),
        certification_count=len(requirements.certifications),
        min_experience_years=requirements.min_experience_years,
        requirements=requirements.model_dump(mode="json"),
    )

    return requirements


def build_jd_embedding_text(requirements: JDRequirements) -> str:
    parts: list[str] = []

    if requirements.mandatory_skills:
        parts.append("Mandatory skills: " + ", ".join(requirements.mandatory_skills))
    if requirements.preferred_skills:
        parts.append("Preferred skills: " + ", ".join(requirements.preferred_skills))
    if requirements.certifications:
        parts.append("Certifications: " + ", ".join(requirements.certifications))
    if requirements.min_experience_years > 0:
        parts.append(
            f"Minimum experience: {requirements.min_experience_years:.1f} years"
        )

    return "\n".join(parts)


def generate_jd_embedding(text: str) -> list[float]:
    return generate_embedding(text)
