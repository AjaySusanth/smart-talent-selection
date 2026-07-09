"""
Celery task for generating AI justifications for top-ranked candidates.

Triggered by the ranking service after computing scores.
Uses Redis caching to avoid redundant LLM calls.
"""

from __future__ import annotations

import json
import time

import redis
import structlog
from celery import Task
from sqlalchemy import select, update

from app.core.config import settings
from app.db.sync_session import get_sync_session
from app.models.candidate import Candidate
from app.models.job_description import JobDescription
from app.models.job_match import JobMatch
from app.services.ranking.justifier import generate_justification
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)

_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days

_redis_url = settings.redis_url
if "ssl_cert_reqs=CERT_NONE" in _redis_url:
    _redis_url = _redis_url.replace("ssl_cert_reqs=CERT_NONE", "ssl_cert_reqs=none")

_redis_client = redis.from_url(_redis_url, decode_responses=True)


def _skill_list(profile: dict) -> list[str]:
    source = profile.get("normalised_skills") or profile.get("skills", [])
    values: list[str] = []
    for skill in source:
        if isinstance(skill, dict):
            name = str(skill.get("name", "")).strip()
        else:
            name = str(skill).strip()
        if name:
            values.append(name)
    return values


def _build_match_context(
    jd_requirements: dict, candidate_profile: dict, score_breakdown: dict
) -> dict:
    required_skills = [
        str(skill).strip()
        for skill in jd_requirements.get("mandatory_skills", [])
        if str(skill).strip()
    ]
    preferred_skills = [
        str(skill).strip()
        for skill in jd_requirements.get("preferred_skills", [])
        if str(skill).strip()
    ]
    candidate_skills = _skill_list(candidate_profile)
    candidate_skill_keys = {skill.casefold() for skill in candidate_skills}
    matched_required_skills = [
        skill for skill in required_skills if skill.casefold() in candidate_skill_keys
    ]
    missing_required_skills = [
        skill
        for skill in required_skills
        if skill.casefold() not in candidate_skill_keys
    ]

    final_score = float(score_breakdown.get("final_score", 0) or 0)
    skill_score = float(score_breakdown.get("skill_score", 0) or 0)
    mandatory_ratio = float(score_breakdown.get("mandatory_ratio", 0) or 0)
    gate_multiplier = float(score_breakdown.get("gate_multiplier", 0) or 0)
    matching_mandatory_skills = int(
        score_breakdown.get("matching_mandatory_skills", 0) or 0
    )

    verdict = "Poor fit"
    if (
        matching_mandatory_skills == 0
        or mandatory_ratio < 0.4
        or skill_score == 0
        or final_score < 45
    ):
        verdict = "Poor fit"
    elif gate_multiplier < 0.7:
        verdict = "Medium fit"
    elif final_score < 65:
        verdict = "Medium fit"
    elif final_score < 80:
        verdict = "Strong fit"

    return {
        **score_breakdown,
        "verdict": verdict,
        "candidate_skills": candidate_skills,
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
        "matched_required_skills": matched_required_skills,
        "missing_required_skills": missing_required_skills,
        "experience_years_required": jd_requirements.get("min_experience_years", 0),
        "experience_years_candidate": float(
            candidate_profile.get("total_experience_years", 0) or 0
        ),
    }


class JustificationTask(Task):
    """Base task with retry config."""

    max_retries = 2
    default_retry_delay = 5


@celery_app.task(
    bind=True,
    base=JustificationTask,
    name="app.workers.tasks.ranking.generate_justification_task",
)
def generate_justification_task(self, jd_id: str, candidate_id: str) -> None:
    """
    Generate a 2-sentence AI justification for a candidate-JD pair.

    Steps:
        1. Check Redis cache
        2. If miss → fetch JD requirements + candidate profile from DB
        3. Call justifier (Gemini primary, Groq fallback)
        4. Store in job_matches.justification_text
        5. Cache in Redis with 7-day TTL
    """
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        jd_id=jd_id,
        candidate_id=candidate_id,
    )

    start_time = time.monotonic()
    logger.info("justification_task_started")

    cache_key = f"justification:{jd_id}:{candidate_id}"

    # Step 1: Check cache
    cached = _redis_client.get(cache_key)
    if cached:
        cached_data = json.loads(cached)
        logger.info(
            "justification_cache_hit",
            model=cached_data.get("model"),
        )
        # Still persist to DB in case it was lost
        _persist_justification(
            jd_id,
            candidate_id,
            cached_data["text"],
            cached_data["model"],
        )
        return

    # Step 2: Fetch data from DB
    session = get_sync_session()
    try:
        jd = session.execute(
            select(JobDescription).where(JobDescription.id == jd_id)
        ).scalar_one_or_none()

        if jd is None:
            logger.error("justification_jd_not_found")
            return

        candidate = session.execute(
            select(Candidate).where(Candidate.id == candidate_id)
        ).scalar_one_or_none()

        if candidate is None:
            logger.error("justification_candidate_not_found")
            return

        jd_requirements = jd.requirements_json or {}
        candidate_profile = candidate.profile_json or {}
        job_match = session.execute(
            select(JobMatch).where(
                JobMatch.jd_id == jd_id,
                JobMatch.candidate_id == candidate_id,
            )
        ).scalar_one_or_none()
        match_context = job_match.score_breakdown_json if job_match else {}

    finally:
        session.close()

    # Step 3: Generate justification
    try:
        text, model_used = generate_justification(
            jd_requirements,
            candidate_profile,
            _build_match_context(jd_requirements, candidate_profile, match_context),
        )
    except ValueError as exc:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        logger.error(
            "justification_generation_failed",
            exc=str(exc),
            duration_ms=duration_ms,
        )
        raise self.retry(exc=exc)

    # Step 4: Persist to DB
    _persist_justification(jd_id, candidate_id, text, model_used)

    # Step 5: Cache in Redis
    cache_value = json.dumps({"text": text, "model": model_used})
    try:
        _redis_client.setex(cache_key, _CACHE_TTL_SECONDS, cache_value)
    except Exception as cache_exc:
        logger.warning("justification_cache_write_failed", exc=str(cache_exc))

    duration_ms = int((time.monotonic() - start_time) * 1000)
    logger.info(
        "justification_task_complete",
        model=model_used,
        duration_ms=duration_ms,
        text_chars=len(text),
    )


def _persist_justification(
    jd_id: str, candidate_id: str, text: str, model: str
) -> None:
    """Write justification to the job_matches row."""
    session = get_sync_session()
    try:
        session.execute(
            update(JobMatch)
            .where(
                JobMatch.jd_id == jd_id,
                JobMatch.candidate_id == candidate_id,
            )
            .values(
                justification_text=text,
                justification_model=model,
            )
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
