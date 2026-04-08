"""
Text extraction orchestrator.

Tries Azure DI first, falls back to PyMuPDF/python-docx on failure.
Returns normalised text ready for the LLM extraction step.
"""

from __future__ import annotations

import structlog

from app.core.exceptions import ParsingError
from app.services.parsing.azure_di_client import extract_text as azure_di_extract
from app.services.parsing.fallback_client import extract_text_docx, extract_text_pdf
from app.services.parsing.text_normaliser import normalise

logger = structlog.get_logger(__name__)

# MIME types that each fallback supports
_PDF_MIME = "application/pdf"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def extract_and_normalise(file_bytes: bytes, mime_type: str) -> str:
    """
    Extract text from a document, with fallback and normalisation.

    Flow:
      1. Try Azure Document Intelligence (primary — layout-aware)
      2. On failure, try the appropriate fallback extractor
      3. Normalise the result (clean encoding, whitespace)

    This function is SYNCHRONOUS — call from Celery workers only.

    Args:
        file_bytes: Raw document bytes
        mime_type: Server-validated MIME type (from python-magic)

    Returns:
        Normalised extracted text

    Raises:
        ParsingError: If both Azure DI and fallback fail
    """
    raw_text = None

    # Step 1: Try Azure DI (primary)
    try:
        raw_text = azure_di_extract(file_bytes, mime_type)
        logger.info("extraction_source", source="azure_di")
    except ParsingError as e:
        logger.warning(
            "azure_di_failed_trying_fallback",
            error=str(e),
            mime_type=mime_type,
        )

        # Step 2: Try fallback based on MIME type
        try:
            if mime_type == _PDF_MIME:
                raw_text = extract_text_pdf(file_bytes)
                logger.info("extraction_source", source="fallback_pdf")
            elif mime_type == _DOCX_MIME:
                raw_text = extract_text_docx(file_bytes)
                logger.info("extraction_source", source="fallback_docx")
            else:
                # Images (JPEG/PNG) have no fallback — Azure DI is the only option
                raise ParsingError(
                    f"Azure DI failed for {mime_type} and no fallback is available. "
                    f"Original error: {e}",
                    source="no_fallback",
                ) from e
        except ParsingError:
            raise

    # Step 3: Normalise
    logger.info(
        "text_extraction_raw_preview",
        raw_chars=len(raw_text),
        raw_preview=raw_text[:1200],
    )

    normalised = normalise(raw_text)

    logger.info(
        "text_extraction_complete",
        raw_chars=len(raw_text),
        normalised_chars=len(normalised),
        normalised_preview=normalised[:1200],
    )

    return normalised
