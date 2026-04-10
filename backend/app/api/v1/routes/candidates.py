"""Routes for candidate operations including statistics."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_api_key
from app.db.session import get_db_session
from app.models.candidate import Candidate
from app.models.resume_upload import ResumeUpload, UploadStatus

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get("/count")
async def get_candidate_counts(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[None, Depends(require_api_key)],
):
    """
    Get candidate statistics for the dashboard.

    **Response:**
    - `total`: Total number of candidate profiles parsed
    - `parsed`: Count of successfully parsed resumes
    - `processing`: Count of resumes currently queued or parsing
    """
    # Total parsed candidates
    total = await session.scalar(select(func.count(Candidate.id))) or 0

    # Parsed resumes
    parsed = (
        await session.scalar(
            select(func.count(ResumeUpload.id)).where(
                ResumeUpload.status == UploadStatus.parsed
            )
        )
        or 0
    )

    # Processing resumes
    processing = (
        await session.scalar(
            select(func.count(ResumeUpload.id)).where(
                ResumeUpload.status.in_([UploadStatus.parsing, UploadStatus.queued])
            )
        )
        or 0
    )

    return {
        "total": total,
        "parsed": parsed,
        "processing": processing,
    }
