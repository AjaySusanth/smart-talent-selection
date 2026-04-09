from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_scoring_config import JobScoringConfig
from app.schemas.scoring_config import ScoringConfigUpdate

logger = structlog.get_logger(__name__)


async def get_scoring_config(session: AsyncSession, job_role_id) -> JobScoringConfig:
    """Fetch the scoring config for a job role, or create default if missing."""
    result = await session.execute(
        select(JobScoringConfig).where(JobScoringConfig.job_role_id == job_role_id)
    )
    config = result.scalar_one_or_none()

    if config is None:
        # Create default config on the fly if not exists
        config = JobScoringConfig(job_role_id=job_role_id)
        session.add(config)
        await session.commit()
        await session.refresh(config)
        logger.info("default_scoring_config_created", job_role_id=str(job_role_id))

    return config


async def update_scoring_config(
    session: AsyncSession, job_role_id, data: ScoringConfigUpdate
) -> JobScoringConfig:
    """Update weights for a specific job role."""
    config = await get_scoring_config(session, job_role_id)

    config.skill_match_weight = data.skill_match_weight
    config.exp_years_weight = data.exp_years_weight
    config.projects_weight = data.projects_weight
    config.prof_exp_weight = data.prof_exp_weight
    config.certs_weight = data.certs_weight
    config.is_customised = True

    await session.commit()
    await session.refresh(config)

    logger.info(
        "scoring_config_updated",
        job_role_id=str(job_role_id),
        weights=data.model_dump(),
    )
    return config


async def reset_scoring_config(session: AsyncSession, job_role_id) -> JobScoringConfig:
    """Restore default weights for a job role."""
    config = await get_scoring_config(session, job_role_id)

    config.skill_match_weight = 40
    config.exp_years_weight = 20
    config.projects_weight = 20
    config.prof_exp_weight = 15
    config.certs_weight = 5
    config.is_customised = False

    await session.commit()
    await session.refresh(config)

    logger.info("scoring_config_reset", job_role_id=str(job_role_id))
    return config
