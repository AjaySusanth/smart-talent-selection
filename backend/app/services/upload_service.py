"""Service for handling resume uploads."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import magic
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.job_role import JobRole
from app.models.resume_upload import ResumeUpload, UploadStatus
from app.services.storage import delete_file, upload_file
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)

# Allowed MIME types for resume uploads
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/png",
}

# Maximum file size: 10 MB
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

# Reusable MIME detector — avoids re-reading the magic database per file
_mime_detector = magic.Magic(mime=True)


async def upload_resume_files(
    session: AsyncSession,
    job_role_id: str,
    files: list[tuple[str, bytes]],
) -> tuple[list[ResumeUpload], list[dict]]:
    """
    Upload multiple resume files with per-file error handling.

    Args:
        session: Database session
        job_role_id: Job role UUID
        files: List of (filename, file_bytes) tuples

    Returns:
        Tuple of (successful_uploads, failed_uploads_info)
        - successful_uploads: List of ResumeUpload objects created and flushed
        - failed_uploads_info: List of dicts with filename, error_message
    """
    successful_uploads = []
    failed_uploads = []

    # Verify job role exists
    role_result = await session.execute(
        select(JobRole).filter(JobRole.id == job_role_id)
    )
    job_role = role_result.scalar_one_or_none()
    if not job_role:
        return [], [
            {"filename": f, "error_message": f"Job role {job_role_id} not found"}
            for f, _ in files
        ]

    for filename, file_bytes in files:
        file_uploaded_to_storage = False
        file_key = None

        try:
            # Validate file size
            if len(file_bytes) > MAX_FILE_SIZE_BYTES:
                failed_uploads.append(
                    {
                        "filename": filename,
                        "error_message": f"File size exceeds {MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f}MB limit",
                    }
                )
                continue

            # Validate MIME type using python-magic (server-side, not extension)
            mime_type = _mime_detector.from_buffer(file_bytes)
            if mime_type not in ALLOWED_MIME_TYPES:
                failed_uploads.append(
                    {
                        "filename": filename,
                        "error_message": f"MIME type '{mime_type}' not allowed. Allowed: {', '.join(ALLOWED_MIME_TYPES)}",
                    }
                )
                continue

            # Generate unique file key for storage
            file_extension = Path(filename).suffix
            file_key = f"{job_role_id}/{uuid4()}{file_extension}"

            # Upload to Supabase storage
            await upload_file(file_bytes, file_key, mime_type)
            file_uploaded_to_storage = True

            # Create database record with initial status
            # PRD: "Atomic: if DB insert fails, delete the uploaded file"
            resume_upload = ResumeUpload(
                job_role_id=job_role_id,
                file_key=file_key,
                original_name=filename,
                mime_type=mime_type,
                file_size_bytes=len(file_bytes),
                status=UploadStatus.uploaded,
            )
            session.add(resume_upload)
            await session.flush()  # Get the ID without committing

            # Enqueue parsing task (Celery)
            try:
                celery_app.send_task(
                    "app.workers.tasks.parse_resume.parse_resume_task",
                    args=[str(resume_upload.id), file_key],
                    queue="default",
                )
                # Update status to queued
                resume_upload.status = UploadStatus.queued
                logger.info(
                    "parsing_job_enqueued",
                    resume_upload_id=str(resume_upload.id),
                    filename=filename,
                )
            except Exception as task_error:
                logger.warning(
                    "task_enqueue_failed",
                    filename=filename,
                    exc=str(task_error),
                )
                # Keep status as 'uploaded' if task enqueueing fails; it can be retried

            successful_uploads.append(resume_upload)

        except Exception as e:
            logger.error("file_processing_error", filename=filename, exc=str(e))

            # Rollback: delete from storage if already uploaded
            if file_uploaded_to_storage and file_key:
                try:
                    await delete_file(file_key)
                    logger.info("storage_rollback_complete", file_key=file_key)
                except Exception as cleanup_error:
                    logger.error(
                        "storage_rollback_failed",
                        file_key=file_key,
                        exc=str(cleanup_error),
                    )

            failed_uploads.append(
                {
                    "filename": filename,
                    "error_message": str(e),
                }
            )

    return successful_uploads, failed_uploads


async def get_upload_status(
    session: AsyncSession, upload_id: str
) -> ResumeUpload | None:
    """Get the status of a resume upload by ID."""
    result = await session.execute(
        select(ResumeUpload).filter(ResumeUpload.id == upload_id)
    )
    return result.scalar_one_or_none()
