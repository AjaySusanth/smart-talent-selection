"""Routes for resume upload operations."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_api_key
from app.db.session import get_db_session
from app.schemas.resume_upload import (
    BatchUploadResponse,
    UploadResponse,
    UploadStatusResponse,
)
from app.services.upload_service import get_upload_status, upload_resume_files

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post("/upload", response_model=BatchUploadResponse, status_code=202)
async def upload_resumes(
    job_role_id: Annotated[str, Form()],
    files: list[UploadFile],
    session: AsyncSession = Depends(get_db_session),
    _: None = Depends(require_api_key),
) -> BatchUploadResponse:
    """
    Batch upload resume files for a job role.

    **Request:**
    - `job_role_id`: UUID of the target job role
    - `files`: Resume files (PDF, DOCX, JPEG, PNG)

    **Response Status:** 202 Accepted (processing in background)

    **Response Body:**
    - `uploaded`: List of successfully uploaded files with IDs
    - `failed`: List of rejected files with error messages

    **Constraints:**
    - Maximum 10 MB per file
    - Allowed MIME types: PDF, DOCX, JPEG, PNG
    - Per-file validation; batch does not fail if individual files error
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided"
        )

    if not job_role_id or not job_role_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="job_role_id is required"
        )

    try:
        # Read file contents into memory
        file_tuples = []
        for upload_file in files:
            if not upload_file.filename:
                continue
            file_bytes = await upload_file.read()
            file_tuples.append((upload_file.filename, file_bytes))

        if not file_tuples:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid files provided",
            )

        # Process uploads with per-file error handling
        successful_uploads, failed_uploads = await upload_resume_files(
            session,
            job_role_id,
            file_tuples,
        )

        # Commit successful uploads to database
        if successful_uploads:
            await session.commit()
        else:
            await session.rollback()

        # Build response
        uploaded_responses = [
            UploadResponse(
                id=str(upload.id),
                original_name=upload.original_name,
                status=upload.status,
                error_message=None,
            )
            for upload in successful_uploads
        ]

        failed_responses = [
            UploadResponse(
                id="",
                original_name=failed["filename"],
                status=None,
                error_message=failed["error_message"],
            )
            for failed in failed_uploads
        ]

        return BatchUploadResponse(
            uploaded=uploaded_responses,
            failed=failed_responses,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("upload_batch_error", exc=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process uploads",
        )


@router.get("/status/{upload_id}", response_model=UploadStatusResponse)
async def check_upload_status(
    upload_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: None = Depends(require_api_key),
) -> UploadStatusResponse:
    """
    Check the current status of a resume upload.

    **Path Parameters:**
    - `upload_id`: UUID of the upload record

    **Response:**
    - `status`: Current state (uploaded, queued, parsing, parsed, failed)
    - `error_message`: Details if parsing failed
    - `file_key`: Storage location if successfully stored
    """
    upload = await get_upload_status(session, str(upload_id))

    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found"
        )

    return UploadStatusResponse(
        id=str(upload.id),
        original_name=upload.original_name,
        status=upload.status,
        error_message=upload.error_message,
        file_key=upload.file_key,
    )
