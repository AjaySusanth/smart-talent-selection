from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobDescription, JobRole, JobScoringConfig
from app.schemas.job_description import JobDescriptionCreate
from app.services.parsing.jd_extractor import (
    build_jd_embedding_text,
    extract_requirements,
    generate_jd_embedding,
)

logger = structlog.get_logger(__name__)


async def _ensure_default_scoring_config(
    session: AsyncSession, job_role_id
) -> JobScoringConfig:
    result = await session.execute(
        select(JobScoringConfig).where(JobScoringConfig.job_role_id == job_role_id)
    )
    config = result.scalar_one_or_none()
    if config is not None:
        return config

    config = JobScoringConfig(job_role_id=job_role_id)
    session.add(config)
    await session.flush()
    return config


async def create_job_description(
    session: AsyncSession,
    payload: JobDescriptionCreate,
) -> JobDescription:
    role_result = await session.execute(
        select(JobRole).where(JobRole.id == payload.job_role_id)
    )
    job_role = role_result.scalar_one_or_none()
    if job_role is None:
        raise ValueError(f"Job role {payload.job_role_id} not found")

    import asyncio

    # Issue #5: Run blocking LLM/Embedding calls in a thread pool
    requirements = await asyncio.to_thread(extract_requirements, payload.raw_text)
    embedding_text = build_jd_embedding_text(requirements)
    embedding = await asyncio.to_thread(generate_jd_embedding, embedding_text)

    # Issue #6: Transactional integrity with explicit rollback
    try:
        jd = JobDescription(
            job_role_id=payload.job_role_id,
            raw_text=payload.raw_text,
            requirements_json=requirements.model_dump(mode="json"),
            embedding=embedding,
            is_active=True,
        )

        session.add(jd)
        await _ensure_default_scoring_config(session, payload.job_role_id)
        await session.commit()
        await session.refresh(jd)

        logger.info(
            "job_description_created",
            jd_id=str(jd.id),
            job_role_id=str(jd.job_role_id),
            embedding_dims=len(embedding),
        )

        return jd

    except Exception as exc:
        await session.rollback()
        logger.error("job_description_creation_failed", exc=str(exc))
        raise


async def get_job_description(
    session: AsyncSession,
    jd_id,
) -> JobDescription | None:
    result = await session.execute(
        select(JobDescription).where(JobDescription.id == jd_id)
    )
    return result.scalar_one_or_none()
