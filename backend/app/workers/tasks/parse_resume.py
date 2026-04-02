"""
Resume parsing Celery task — Phase 2 skeleton.

This task is enqueued by the upload service after a resume is stored.
The actual parsing logic (Azure DI, LLM extraction, embedding) will be
implemented in Phase 3 (Tasks 3.1–3.7).
"""

from __future__ import annotations

import structlog
from celery import Task

from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


class ParseResumeTask(Task):
    """Base task with retry config and failure logging."""

    max_retries = 3
    default_retry_delay = 2  # base delay in seconds

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            "parse_resume_task_final_failure",
            task_id=task_id,
            resume_upload_id=str(args[0]) if args else "unknown",
            exc=str(exc),
        )
        # TODO (Phase 3): Update resume_uploads.status = 'failed' in DB


@celery_app.task(bind=True, base=ParseResumeTask, name="app.workers.tasks.parse_resume.parse_resume_task")
def parse_resume_task(self, resume_upload_id: str, file_key: str) -> None:
    """
    Main entry point for the resume parsing pipeline.

    Args:
        resume_upload_id: UUID of the resume_uploads row
        file_key: Supabase Storage object key

    Phase 3 will implement:
        1. Download file from Supabase
        2. Azure DI text extraction
        3. Deterministic field extraction (regex)
        4. NER via HuggingFace
        5. LLM structured extraction (Gemini Flash)
        6. Skill normalisation (Groq 8B)
        7. Summary generation (Groq 70B)
        8. Embedding generation (OpenAI)
        9. Store candidate profile in DB
    """
    # Bind context for structured log tracing
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        resume_upload_id=resume_upload_id,
        file_key=file_key,
    )

    logger.info("parsing_task_received")

    try:
        # TODO (Phase 3): Wire to profile_builder.build()
        logger.info(
            "parsing_task_placeholder",
            message="Task received but parsing pipeline not yet implemented",
        )

    except Exception as exc:
        retry_count = self.request.retries
        countdown = self.default_retry_delay ** (retry_count + 1)
        logger.warning(
            "parsing_task_retry",
            exc=str(exc),
            retry=retry_count + 1,
            max_retries=self.max_retries,
            countdown=countdown,
        )
        raise self.retry(exc=exc, countdown=countdown)
