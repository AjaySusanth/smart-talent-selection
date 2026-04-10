"""Routes for candidate operations including statistics."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_api_key
from app.db.session import get_db_session
from app.models.candidate import Candidate
from app.models.resume_upload import ResumeUpload, UploadStatus
from app.services.storage import delete_file

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


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(
    candidate_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[None, Depends(require_api_key)],
) -> None:
    """Delete candidate profile and linked resume upload; also remove file from storage."""
    candidate = await session.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    upload = await session.get(ResumeUpload, candidate.resume_upload_id)
    file_key: str | None = None

    if upload is not None:
        file_key = upload.file_key
        await session.delete(upload)
    else:
        await session.delete(candidate)

    await session.commit()

    if file_key:
        try:
            await delete_file(file_key)
        except Exception:
            # DB deletion succeeded; storage cleanup is best-effort.
            pass
