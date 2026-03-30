from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_api_key
from app.db.session import get_db_session
from app.schemas.job_role import JobRoleCreate, JobRoleResponse
from app.services.job_role_service import create_job_role, list_job_roles

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
