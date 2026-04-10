"""Routes for resume upload operations."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID
from uuid import uuid4
import hashlib

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form, status, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_api_key
from app.db.session import get_db_session
from app.models.resume_upload import ResumeUpload, UploadStatus
from app.schemas.resume_upload import (
    BatchUploadResponse,
    UploadResponse,
    UploadStatusResponse,
)
from app.services.upload_service import get_upload_status, upload_resume_files
from app.services.storage import get_presigned_url, delete_file
from app.workers.celery_app import celery_app

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


@router.get("/{upload_id}/file")
async def get_resume_file_url(
    upload_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: None = Depends(require_api_key),
):
    """
    Get a signed URL for downloading a resume file.

    **Path Parameters:**
    - `upload_id`: UUID of the resume upload

    **Response:**
    - `url`: Signed URL (valid for 60 seconds)
    - `filename`: Original filename
    - `mime_type`: Content type
    """
    upload = await session.get(ResumeUpload, upload_id)
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found",
        )

    try:
        signed_url = await get_presigned_url(upload.file_key, expiry_seconds=60)
    except Exception as exc:
        logger.error(
            "generate_signed_url_error", upload_id=str(upload_id), exc=str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to generate file download link",
        ) from exc

    return {
        "url": signed_url,
        "filename": upload.original_name,
        "mime_type": upload.mime_type,
    }


@router.get("")
async def list_resumes(
    job_role_id: Annotated[UUID, Query()],
    session: AsyncSession = Depends(get_db_session),
    _: None = Depends(require_api_key),
):
    """List upload records for a job role via query param contract."""
    result = await session.execute(
        select(ResumeUpload)
        .where(ResumeUpload.job_role_id == job_role_id)
        .order_by(ResumeUpload.uploaded_at.desc())
    )
    uploads = result.scalars().all()
    return [
        {
            "id": str(upload.id),
            "original_name": upload.original_name,
            "status": upload.status,
            "error_message": upload.error_message,
            "uploaded_at": upload.uploaded_at,
        }
        for upload in uploads
    ]


@router.get("/jobs/{job_role_id}")
async def list_resumes_for_role(
    job_role_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: None = Depends(require_api_key),
):
    """
    List all resume uploads for a specific job role.

    **Path Parameters:**
    - `job_role_id`: UUID of the job role

    **Response:** Array of upload records with status
    """
    result = await session.execute(
        select(ResumeUpload)
        .where(ResumeUpload.job_role_id == job_role_id)
        .order_by(ResumeUpload.uploaded_at.desc())
    )
    uploads = result.scalars().all()

    return [
        {
            "id": str(upload.id),
            "original_name": upload.original_name,
            "status": upload.status,
            "error_message": upload.error_message,
            "uploaded_at": upload.uploaded_at,
        }
        for upload in uploads
    ]


@router.post("/{upload_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_resume_parsing(
    upload_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: None = Depends(require_api_key),
):
    """Manually requeue parsing for a failed resume upload."""
    upload = await session.get(ResumeUpload, upload_id)
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found",
        )

    if upload.status == UploadStatus.parsing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Upload is already parsing",
        )

    if upload.status == UploadStatus.queued:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Upload is already queued",
        )

    # Requeue regardless of prior failure reason; this is a manual override action.
    await session.execute(
        update(ResumeUpload)
        .where(ResumeUpload.id == upload_id)
        .values(status=UploadStatus.queued, error_message=None)
    )
    await session.commit()

    idempotency_key = hashlib.sha256(
        f"{upload.file_key}:{uuid4()}".encode()
    ).hexdigest()[:32]

    celery_app.send_task(
        "app.workers.tasks.parse_resume.parse_resume_task",
        args=[str(upload.id), upload.file_key],
        task_id=idempotency_key,
    )

    return {
        "id": str(upload.id),
        "status": "queued",
        "message": "Parsing retry has been queued",
    }


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume_upload(
    upload_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: None = Depends(require_api_key),
):
    """Delete a resume upload and associated candidate data (DB cascade)."""
    upload = await session.get(ResumeUpload, upload_id)
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found",
        )

    if upload.status in (UploadStatus.queued, UploadStatus.parsing):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete while parsing is in progress",
        )

    file_key = upload.file_key
    await session.delete(upload)
    await session.commit()

    # Best-effort storage cleanup; DB delete is already committed.
    try:
        await delete_file(file_key)
    except Exception as exc:
        logger.warning(
            "resume_storage_delete_failed", upload_id=str(upload_id), exc=str(exc)
        )
