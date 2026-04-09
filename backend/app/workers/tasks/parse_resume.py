"""
Resume parsing Celery task.

Enqueued by the upload service after a resume is stored in Supabase.

Pipeline stages:
  1. Download file from Supabase Storage
  2. Detect MIME type
  2.5. Extract hyperlinks from DOCX/PDF structure (before text extraction)
  3. Extract and normalise text (Azure DI → fallback)
  4. Deterministic field extraction (regex)
  5. NER via HuggingFace Inference API
    6. LLM structured extraction (Groq llama-3.3-70b-versatile)
     - Post-processing: regex overlay, hyperlink overlay, issuer normalisation
    7. Skill normalisation (deterministic aliases + Groq fallback)
    8. Embedding generation (structured text + Azure OpenAI vector)
    9. Candidate persistence (candidate row + upload status parsed)

TODO: Task 4+ ranking and scoring pipeline.
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
from app.services.parsing.candidate_persister import persist_candidate
from app.services.parsing.embedding_builder import build_embedding_text
from app.services.parsing.embedding_generator import generate_embedding
from app.services.parsing.gemini_extractor import extract_structured_profile
from app.services.parsing.hyperlink_extractor import extract_hyperlinks
from app.services.parsing.ner_extractor import extract_entities
from app.services.parsing.regex_extractor import extract_deterministic_fields
from app.services.parsing.skill_normaliser import normalise_skills
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
    See module docstring for the full stage list.
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

        # Step 2.5: Extract hyperlinks from file structure (before text extraction)
        # This reads the real href values from DOCX XML rels / PDF annotations.
        # Must run BEFORE Azure DI because DI only returns display text.
        logger.info("hyperlink_extraction_started")
        hyperlinks = extract_hyperlinks(file_bytes, mime_type)
        logger.info(
            "hyperlink_extraction_finished",
            total_hrefs=len(hyperlinks.get("raw_hrefs", [])),
            has_linkedin=hyperlinks.get("linkedin_url") is not None,
            has_github=hyperlinks.get("github_url") is not None,
            project_url_count=len(hyperlinks.get("project_urls", [])),
            linkedin_url=hyperlinks.get("linkedin_url"),
            github_url=hyperlinks.get("github_url"),
            project_urls=hyperlinks.get("project_urls", []),
            raw_hrefs=hyperlinks.get("raw_hrefs", []),
        )

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

        # Step 5: Named Entity Recognition (Task 3.3)
        logger.info("ner_extraction_started")
        ner_result = extract_entities(extracted_text)
        logger.info(
            "ner_extraction_finished",
            **ner_result.to_dict(),
        )

        # Step 6: LLM Structured Extraction (Task 3.4)
        # Groq receives text + regex + NER hints.
        # Post-processing overlays regex data, then hyperlinks (highest priority),
        # then resolves missing certification issuers.
        logger.info("gemini_extraction_started")
        candidate_profile = extract_structured_profile(
            text=extracted_text,
            regex_hints=regex_result,
            ner_hints=ner_result,
            hyperlinks=hyperlinks,
        )
        logger.info(
            "gemini_extraction_finished",
            full_name=candidate_profile.full_name,
            skills_count=len(candidate_profile.skills),
            experience_count=len(candidate_profile.experience),
            education_count=len(candidate_profile.education),
            total_exp_years=candidate_profile.total_experience_years,
        )

        # Step 7: Skill Normalisation (Task 3.5)
        candidate_profile.normalised_skills = normalise_skills(candidate_profile.skills)

        # Step 8: Embedding Generation (Task 3.7)
        embedding_text = build_embedding_text(candidate_profile)
        embedding_vector = generate_embedding(embedding_text)

        # Step 9: Candidate Persistence (Task 3.6)
        session = get_sync_session()
        try:
            candidate = persist_candidate(
                session=session,
                resume_upload_id=resume_upload_id,
                raw_text=extracted_text,
                profile=candidate_profile,
                embedding_text=embedding_text,
                embedding_vector=embedding_vector,
            )
        finally:
            session.close()

        duration_ms = int((time.monotonic() - start_time) * 1000)
        logger.info(
            "parsing_task_pipeline_complete",
            duration_ms=duration_ms,
            extracted_chars=len(extracted_text),
            embedding_chars=len(embedding_text),
            embedding_dims=len(embedding_vector),
            candidate_id=str(candidate.id),
            profile_json=candidate_profile.model_dump(),
        )

    except ParsingError as exc:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        logger.error(
            "parsing_error",
            source=exc.source,
            exc=str(exc),
            duration_ms=duration_ms,
        )
        if settings.environment == "development":
            # In dev, don't retry to save on DI limits/time
            raise exc

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
        if settings.environment == "development":
            # In dev, don't retry to save on DI limits/time
            raise exc

        retry_count = self.request.retries
        countdown = self.default_retry_delay ** (retry_count + 1)
        raise self.retry(exc=exc, countdown=countdown)
