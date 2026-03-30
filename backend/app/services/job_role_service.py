from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobRole, ResumeUpload
from app.schemas.job_role import JobRoleCreate


async def create_job_role(session: AsyncSession, data: JobRoleCreate) -> JobRole:
    job_role = JobRole(title=data.title, description=data.description)
    session.add(job_role)
    await session.commit()
    await session.refresh(job_role)
    return job_role


async def list_job_roles(session: AsyncSession) -> list[tuple[JobRole, int]]:
    stmt = (
        select(JobRole, func.count(ResumeUpload.id).label("resume_count"))
        .outerjoin(ResumeUpload, ResumeUpload.job_role_id == JobRole.id)
        .group_by(JobRole.id)
        .order_by(JobRole.created_at.desc())
    )
    result = await session.execute(stmt)
    return [(row[0], int(row[1])) for row in result.all()]
