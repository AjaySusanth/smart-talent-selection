"""
Azure Document Intelligence client for layout-aware text extraction.

Watchouts applied (see docs/azure_di_watchouts.md):
  W3 — Uses result.paragraphs, NOT result.content (two-column fix)
  W4 — MIME type comes from python-magic (validated upstream)
  W5 — Warns on suspiciously short extraction (scanned PDFs)
  W6 — Logs page count and warns on possible F0 truncation
  W7 — Skips pageHeader and pageFooter paragraphs
"""

from __future__ import annotations

import time

import structlog
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError

from app.core.config import settings
from app.core.exceptions import ParsingError

logger = structlog.get_logger(__name__)

# Paragraph roles to exclude from extracted text (Watchout 7)
_SKIP_ROLES = {"pageHeader", "pageFooter"}

# Minimum character count before flagging as suspicious (Watchout 5)
_MIN_EXTRACTION_LENGTH = 100

# File size heuristic for truncation warning (Watchout 6)
_TRUNCATION_SIZE_THRESHOLD = 150_000  # bytes


def _get_client() -> DocumentIntelligenceClient:
    """Create a new Azure DI client instance."""
    return DocumentIntelligenceClient(
        endpoint=settings.azure_di_endpoint,
        credential=AzureKeyCredential(settings.azure_di_key),
    )


def _extract_ordered_text(result) -> str:
    """
    Build clean text from paragraphs and tables in reading order.

    Uses result.paragraphs (NOT result.content) for two-column fix (Watchout 3).
    Also extracts result.tables — skills grids and education tables are common
    in resumes and are not included in result.paragraphs.
    """
    parts = []

    # Extract paragraphs in reading order (Watchout 3 & 7)
    if result.paragraphs:
        for para in result.paragraphs:
            if para.role in _SKIP_ROLES or not para.content.strip():
                continue
            parts.append(para.content.strip())

    # Extract table content — separate from paragraphs in Azure DI result
    if result.tables:
        for table in result.tables:
            table_text = _table_to_text(table)
            if table_text:
                parts.append(table_text)

    return "\n".join(parts)


def _table_to_text(table) -> str:
    """
    Convert an Azure DI table result to pipe-delimited text rows.

    Azure DI returns table cells with row/column indices.
    We reconstruct row by row and join cells with ' | '.
    """
    if not table.cells:
        return ""

    max_row = max(c.row_index for c in table.cells) + 1
    max_col = max(c.column_index for c in table.cells) + 1

    # Build a 2D grid from cell positions
    grid = [[""] * max_col for _ in range(max_row)]
    for cell in table.cells:
        grid[cell.row_index][cell.column_index] = cell.content.strip()

    # Convert each row to pipe-delimited text, skip empty rows
    rows = []
    for row in grid:
        row_text = " | ".join(row).strip()
        if row_text:
            rows.append(row_text)

    return "\n".join(rows)


def extract_text(file_bytes: bytes, mime_type: str) -> str:
    """
    Extract layout-aware text from a document using Azure Document Intelligence.

    This function is SYNCHRONOUS and blocks the calling thread while Azure
    processes the document (2–8 seconds). It must only be called from a
    Celery worker, never from a FastAPI async route handler (Watchout 2).

    Args:
        file_bytes: Raw document bytes
        mime_type: MIME type detected by python-magic (not from extension)

    Returns:
        Extracted text in reading order, with headers/footers removed

    Raises:
        ParsingError: If Azure DI fails or returns no usable text
    """
    client = _get_client()
    start_time = time.monotonic()

    try:
        logger.info(
            "azure_di_extraction_started",
            file_size_bytes=len(file_bytes),
            mime_type=mime_type,
        )

        # Send document to Azure DI for layout analysis
        # SDK expects body as IO[bytes] directly
        import io
        poller = client.begin_analyze_document(
            model_id="prebuilt-layout",
            body=io.BytesIO(file_bytes),
            content_type="application/octet-stream",
        )

        # This blocks until Azure returns the result (Watchout 2 — OK in Celery)
        result = poller.result()

        duration_ms = int((time.monotonic() - start_time) * 1000)

        # Log page count (Watchout 6)
        page_count = len(result.pages) if result.pages else 0

        logger.info(
            "azure_di_extraction_complete",
            pages_analysed=page_count,
            file_size_bytes=len(file_bytes),
            duration_ms=duration_ms,
        )

        # Warn on possible F0 truncation (Watchout 6)
        if page_count == 2 and len(file_bytes) > _TRUNCATION_SIZE_THRESHOLD:
            logger.warning(
                "possible_page_truncation",
                pages_analysed=page_count,
                file_size_bytes=len(file_bytes),
                hint="F0 tier limit — upgrade to S0 to analyse all pages",
            )

        # DEBUG: Log what Azure DI actually returned
        para_count = len(result.paragraphs) if result.paragraphs else 0
        table_count = len(result.tables) if result.tables else 0
        logger.info(
            "azure_di_result_structure",
            paragraph_count=para_count,
            table_count=table_count,
            has_content=bool(result.content),
            content_length=len(result.content) if result.content else 0,
        )

        # Log first 3 individual paragraphs to verify reading order
        if result.paragraphs:
            for i, para in enumerate(result.paragraphs[:3]):
                logger.info(
                    "azure_di_paragraph_sample",
                    index=i,
                    role=para.role,
                    text=para.content[:120] if para.content else "",
                )

        # Build text from paragraphs in reading order (Watchout 3 & 7)
        extracted_text = _extract_ordered_text(result)

        logger.info(
            "azure_di_extracted_text_preview",
            extracted_char_count=len(extracted_text),
            extracted_preview=extracted_text[:1200],
        )

        # Check for suspiciously short extraction (Watchout 5)
        if len(extracted_text.strip()) < _MIN_EXTRACTION_LENGTH:
            logger.warning(
                "extraction_suspiciously_short",
                char_count=len(extracted_text),
                page_count=page_count,
                hint="Possible scanned PDF — OCR quality may be low",
            )
            # Do NOT raise — continue with what we have.
            # The profile_builder will set is_low_confidence = True downstream.

        if not extracted_text.strip():
            raise ParsingError(
                "Azure DI returned no extractable text for the uploaded file.",
                source="azure_di",
            )

        return extracted_text

    except ParsingError:
        raise
    except HttpResponseError as e:
        logger.error(
            "azure_di_http_error",
            status_code=e.status_code,
            error_code=e.error.code if e.error else None,
            message=str(e),
            duration_ms=int((time.monotonic() - start_time) * 1000),
        )
        raise ParsingError(
            f"Azure DI request failed: {e.status_code} — {e.message}",
            source="azure_di",
        ) from e
    except Exception as e:
        logger.error(
            "azure_di_unexpected_error",
            exc=str(e),
            duration_ms=int((time.monotonic() - start_time) * 1000),
        )
        raise ParsingError(
            f"Unexpected error during Azure DI extraction: {e}",
            source="azure_di",
        ) from e
