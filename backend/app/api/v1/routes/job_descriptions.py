from __future__ import annotations

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RankingError
from app.core.security import require_api_key
from app.db.session import get_db_session
from app.schemas.job_description import (
    CandidateRankingResult,
    JDRequirements,
    JobDescriptionCreate,
    JobDescriptionRankingResponse,
    JobDescriptionRead,
)
from app.services.jd.manager import create_job_description, get_job_description
from app.services.ranking.ranking_service import get_top_candidates

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/jd", tags=["job-descriptions"])


@router.post("", response_model=JobDescriptionRead, status_code=status.HTTP_201_CREATED)
async def create_job_description_endpoint(
    payload: JobDescriptionCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[None, Depends(require_api_key)],
) -> JobDescriptionRead:
    try:
        jd = await create_job_description(session, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except Exception as exc:
        logger.error("create_job_description_failed", exc=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create job description",
        ) from exc

    requirements = JDRequirements.model_validate(jd.requirements_json)
    return JobDescriptionRead(
        id=jd.id,
        job_role_id=jd.job_role_id,
        raw_text=jd.raw_text,
        requirements=requirements,
        is_active=jd.is_active,
        created_at=jd.created_at,
        status="ready" if jd.embedding is not None else "pending",
    )


@router.get("/{jd_id}", response_model=JobDescriptionRead)
async def get_job_description_endpoint(
    jd_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[None, Depends(require_api_key)],
) -> JobDescriptionRead:
    jd = await get_job_description(session, jd_id)
    if jd is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="JD not found"
        )

    requirements = JDRequirements.model_validate(jd.requirements_json)
    return JobDescriptionRead(
        id=jd.id,
        job_role_id=jd.job_role_id,
        raw_text=jd.raw_text,
        requirements=requirements,
        is_active=jd.is_active,
        created_at=jd.created_at,
        status="ready" if jd.embedding is not None else "pending",
    )


@router.get("/{jd_id}/ranking", response_model=JobDescriptionRankingResponse)
async def get_jd_ranking_endpoint(
    jd_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[None, Depends(require_api_key)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> JobDescriptionRankingResponse:
    try:
        ranked_rows, total_candidates = await get_top_candidates(
            session=session,
            jd_id=jd_id,
            limit=limit,
        )
    except RankingError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except Exception as exc:
        logger.error("get_jd_ranking_failed", jd_id=str(jd_id), exc=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rank candidates for this JD",
        ) from exc

    return JobDescriptionRankingResponse(
        jd_id=jd_id,
        total_candidates=total_candidates,
        returned_candidates=len(ranked_rows),
        candidates=[
            CandidateRankingResult.model_validate(item) for item in ranked_rows
        ],
    )
