"""
Resume parsing Celery task.

Enqueued by the upload service after a resume is stored in Supabase.
Currently implements: file download → text extraction → status update.
Phase 3 Tasks 3.2–3.7 will add LLM extraction, NER, skill normalisation,
summary generation, and embedding.
"""

from __future__ import annotations

import time

import magic
import structlog
from celery import Task
from sqlalchemy import update

from app.core.config import settings
from app.core.exceptions import ParsingError
from app.db.sync_session import get_sync_session
from app.models.resume_upload import ResumeUpload, UploadStatus
from app.services.parsing.regex_extractor import extract_deterministic_fields
from app.services.parsing.text_extractor import extract_and_normalise
from app.services.storage import get_supabase_client
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)

_mime_detector = magic.Magic(mime=True)  # initialised once on worker startup


def _download_file(file_key: str) -> bytes:
    """Download file bytes from Supabase Storage (synchronous)."""
    client = get_supabase_client()
    response = client.storage.from_(settings.supabase_storage_bucket).download(file_key)
    return response


def _update_status(resume_upload_id: str, status: UploadStatus, error_message: str | None = None):
    """Update resume upload status using a synchronous DB session."""
    session = get_sync_session()
    try:
        stmt = (
            update(ResumeUpload)
            .where(ResumeUpload.id == resume_upload_id)
            .values(status=status, error_message=error_message)
        )
        session.execute(stmt)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class ParseResumeTask(Task):
    """Base task with retry config and failure logging."""

    max_retries = 3
    default_retry_delay = 2  # base delay in seconds

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        resume_upload_id = str(args[0]) if args else "unknown"
        logger.error(
            "parse_resume_task_final_failure",
            task_id=task_id,
            resume_upload_id=resume_upload_id,
            exc=str(exc),
        )
        # Mark as failed in DB after all retries exhausted
        if resume_upload_id != "unknown":
            try:
                _update_status(resume_upload_id, UploadStatus.failed, str(exc))
            except Exception as db_err:
                logger.error("failed_to_update_status_on_failure", exc=str(db_err))


@celery_app.task(
    bind=True,
    base=ParseResumeTask,
    name="app.workers.tasks.parse_resume.parse_resume_task",
)
def parse_resume_task(self, resume_upload_id: str, file_key: str) -> None:
    """
    Main entry point for the resume parsing pipeline.

    Current implementation (Task 3.1):
        1. Download file from Supabase Storage
        2. Extract and normalise text (Azure DI → fallback)
        3. Update status in DB

    TODO (Tasks 3.2–3.7):
        4. Deterministic field extraction (regex)
        5. NER via HuggingFace
        6. LLM structured extraction (Gemini Flash)
        7. Skill normalisation (Groq 8B)
        8. Summary generation (Groq 70B)
        9. Embedding generation (OpenAI)
        10. Store candidate profile in DB
    """
    # Bind context for structured log tracing
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        resume_upload_id=resume_upload_id,
        file_key=file_key,
    )

    start_time = time.monotonic()
    logger.info("parsing_task_started")

    try:
        # Update status to 'parsing'
        _update_status(resume_upload_id, UploadStatus.parsing)

        # Step 1: Download file from Supabase
        logger.info("downloading_file")
        file_bytes = _download_file(file_key)
        logger.info("file_downloaded", file_size_bytes=len(file_bytes))

        # Step 2: Detect MIME type from the actual bytes
        mime_type = _mime_detector.from_buffer(file_bytes)

        # Step 3: Extract and normalise text
        logger.info("text_extraction_started")
        extracted_text = extract_and_normalise(file_bytes, mime_type)
        logger.info(
            "text_extraction_finished",
            char_count=len(extracted_text),
        )

        # Step 4: Deterministic field extraction (Task 3.2)
        logger.info("regex_extraction_started")
        regex_result = extract_deterministic_fields(extracted_text)
        logger.info(
            "regex_extraction_finished",
            **regex_result.to_dict(),
        )

        # TODO (Tasks 3.3–3.7): Pass extracted_text + regex_result to the AI pipeline
        # For now, log results and keep status as 'parsing'
        # until the full pipeline is wired up

        duration_ms = int((time.monotonic() - start_time) * 1000)
        logger.info(
            "parsing_task_pipeline_complete",
            duration_ms=duration_ms,
            extracted_chars=len(extracted_text),
            text_preview=extracted_text[:1000] + "..." if len(extracted_text) > 1000 else extracted_text,
            regex_fields=regex_result.to_dict(),
        )

    except ParsingError as exc:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        logger.error(
            "parsing_error",
            source=exc.source,
            exc=str(exc),
            duration_ms=duration_ms,
        )
        retry_count = self.request.retries
        countdown = self.default_retry_delay ** (retry_count + 1)
        raise self.retry(exc=exc, countdown=countdown)

    except Exception as exc:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        logger.error(
            "parsing_task_unexpected_error",
            exc=str(exc),
            duration_ms=duration_ms,
        )
        retry_count = self.request.retries
        countdown = self.default_retry_delay ** (retry_count + 1)
        raise self.retry(exc=exc, countdown=countdown)
