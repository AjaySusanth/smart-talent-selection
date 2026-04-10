from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_api_key
from app.db.session import get_db_session
from app.models.job_role import JobRole
from app.schemas.job_role import JobRoleCreate, JobRoleUpdate, JobRoleResponse
from app.schemas.job_description import JDRequirements, JobDescriptionRead
from app.schemas.scoring_config import ScoringConfigResponse, ScoringConfigUpdate
from app.services.job_role_service import create_job_role, list_job_roles
from app.services.jd.manager import list_job_descriptions_for_role
from app.services.scoring_config_service import (
    get_scoring_config,
    reset_scoring_config,
    update_scoring_config,
)

router = APIRouter(prefix="/job-roles", tags=["job-roles"])


@router.post("", response_model=JobRoleResponse, status_code=status.HTTP_201_CREATED)
async def create_job_role_endpoint(
    payload: JobRoleCreate,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[None, Depends(require_api_key)],
) -> JobRoleResponse:
    job_role = await create_job_role(db, payload)
    return JobRoleResponse(
        id=job_role.id,
        title=job_role.title,
        description=job_role.description,
        is_active=job_role.is_active,
        created_at=job_role.created_at,
        updated_at=job_role.updated_at,
        resume_count=0,
    )


@router.get("", response_model=list[JobRoleResponse])
async def list_job_roles_endpoint(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[None, Depends(require_api_key)],
) -> list[JobRoleResponse]:
    rows = await list_job_roles(db)
    return [
        JobRoleResponse(
            id=job_role.id,
            title=job_role.title,
            description=job_role.description,
            is_active=job_role.is_active,
            created_at=job_role.created_at,
            updated_at=job_role.updated_at,
            resume_count=resume_count,
        )
        for job_role, resume_count in rows
    ]


@router.get("/{id}/jds", response_model=list[JobDescriptionRead])
async def list_jds_for_role_endpoint(
    id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[None, Depends(require_api_key)],
) -> list[JobDescriptionRead]:
    jds = await list_job_descriptions_for_role(db, id)
    return [
        JobDescriptionRead(
            id=jd.id,
            job_role_id=jd.job_role_id,
            raw_text=jd.raw_text,
            requirements=JDRequirements.model_validate(jd.requirements_json),
            is_active=jd.is_active,
            created_at=jd.created_at,
            status="ready" if jd.embedding is not None else "pending",
        )
        for jd in jds
    ]


@router.get("/{id}/scoring-config", response_model=ScoringConfigResponse)
async def get_scoring_config_endpoint(
    id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[None, Depends(require_api_key)],
) -> ScoringConfigResponse:
    config = await get_scoring_config(db, id)
    return ScoringConfigResponse.model_validate(config)


@router.put("/{id}/scoring-config", response_model=ScoringConfigResponse)
async def update_scoring_config_endpoint(
    id: UUID,
    payload: ScoringConfigUpdate,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[None, Depends(require_api_key)],
) -> ScoringConfigResponse:
    config = await update_scoring_config(db, id, payload)
    return ScoringConfigResponse.model_validate(config)


@router.post("/{id}/scoring-config/reset", response_model=ScoringConfigResponse)
async def reset_scoring_config_endpoint(
    id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[None, Depends(require_api_key)],
) -> ScoringConfigResponse:
    config = await reset_scoring_config(db, id)
    return ScoringConfigResponse.model_validate(config)


@router.patch("/{id}", response_model=JobRoleResponse)
async def update_job_role_endpoint(
    id: UUID,
    payload: JobRoleUpdate,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[None, Depends(require_api_key)],
) -> JobRoleResponse:
    """Partially update a job role (title and/or description)."""
    # Build update dict with only non-None values
    update_data = payload.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    await db.execute(update(JobRole).where(JobRole.id == id).values(**update_data))
    await db.commit()

    # Fetch updated role
    result = await db.execute(select(JobRole).where(JobRole.id == id))
    job_role = result.scalar_one_or_none()
    if not job_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job role not found",
        )

    # Count resume uploads for this role
    from sqlalchemy import func
    from app.models.resume_upload import ResumeUpload

    count_result = await db.execute(
        select(func.count(ResumeUpload.id)).where(ResumeUpload.job_role_id == id)
    )
    resume_count = count_result.scalar() or 0

    return JobRoleResponse(
        id=job_role.id,
        title=job_role.title,
        description=job_role.description,
        is_active=job_role.is_active,
        created_at=job_role.created_at,
        updated_at=job_role.updated_at,
        resume_count=resume_count,
    )


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_job_role_endpoint(
    id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[None, Depends(require_api_key)],
) -> None:
    """Soft delete a job role by setting is_active=False."""
    result = await db.execute(select(JobRole).where(JobRole.id == id))
    job_role = result.scalar_one_or_none()
    if not job_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job role not found",
        )

    await db.execute(update(JobRole).where(JobRole.id == id).values(is_active=False))
    await db.commit()


@router.post("/{id}/activate", status_code=status.HTTP_204_NO_CONTENT)
async def activate_job_role_endpoint(
    id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[None, Depends(require_api_key)],
) -> None:
    """Activate a previously deactivated job role."""
    result = await db.execute(select(JobRole).where(JobRole.id == id))
    job_role = result.scalar_one_or_none()
    if not job_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job role not found",
        )

    await db.execute(update(JobRole).where(JobRole.id == id).values(is_active=True))
    await db.commit()
