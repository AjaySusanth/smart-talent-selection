"""
Fallback text extraction clients.

Called when Azure Document Intelligence raises a ParsingError.
These are simpler extractors — they do NOT handle two-column layouts
as well as Azure DI, but they are free and work offline.
"""

from __future__ import annotations

import io

import structlog

from app.core.exceptions import ParsingError

logger = structlog.get_logger(__name__)


def extract_text_pdf(file_bytes: bytes) -> str:
    """
    Extract text from a PDF using PyMuPDF (fitz).

    Concatenates text from all pages in order. Does not handle
    two-column layouts — use Azure DI as the primary extractor.

    Args:
        file_bytes: Raw PDF bytes

    Returns:
        Extracted text

    Raises:
        ParsingError: If the PDF cannot be opened or contains no text
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages_text = []

        for page_num, page in enumerate(doc):
            # Use "blocks" mode to get text with position data
            # Each block: (x0, y0, x1, y1, text, block_no, block_type)
            # Sort by vertical band (y bucketed to 20px rows) then horizontal (x)
            # to approximate correct reading order for two-column layouts
            blocks = page.get_text("blocks")
            blocks_sorted = sorted(
                blocks,
                key=lambda b: (round(b[1] / 20), b[0])  # (row_band, x_position)
            )
            page_text = "\n".join(
                b[4].strip() for b in blocks_sorted
                if b[4].strip() and b[6] == 0  # block_type 0 = text (skip images)
            )
            if page_text:
                pages_text.append(page_text)

        doc.close()

        full_text = "\n\n".join(pages_text)

        if not full_text.strip():
            raise ParsingError(
                "PyMuPDF extracted no text from the PDF — "
                "the file may be a scanned image or corrupted.",
                source="fallback_pdf",
            )

        logger.info(
            "fallback_pdf_extraction_complete",
            pages_extracted=len(pages_text),
            char_count=len(full_text),
        )

        return full_text

    except ParsingError:
        raise
    except Exception as e:
        logger.error("fallback_pdf_extraction_failed", exc=str(e))
        raise ParsingError(
            f"PyMuPDF fallback failed: {e}",
            source="fallback_pdf",
        ) from e


def extract_text_docx(file_bytes: bytes) -> str:
    """
    Extract text from a DOCX file using python-docx.

    Reads paragraphs in document order. Does NOT support
    legacy .doc format (binary Word) — only .docx (XML-based).

    Args:
        file_bytes: Raw DOCX bytes

    Returns:
        Extracted text

    Raises:
        ParsingError: If the DOCX cannot be opened or contains no text
    """
    try:
        from docx import Document

        doc = Document(io.BytesIO(file_bytes))
        parts = []

        # Iterate body elements in document order to preserve paragraph + table sequence
        _WML_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

        for element in doc.element.body:
            tag = element.tag.split("}")[-1]  # strip XML namespace prefix

            if tag == "p":
                # Paragraph element — join all run text
                text = "".join(element.itertext()).strip()
                if text:
                    parts.append(text)

            elif tag == "tbl":
                # Table element — extract row by row as pipe-delimited text
                for row in element.findall(f".//{{{_WML_NS}}}tr"):
                    cells = row.findall(f".//{{{_WML_NS}}}tc")
                    row_text = " | ".join(
                        "".join(c.itertext()).strip() for c in cells
                    )
                    if row_text.strip():
                        parts.append(row_text)

        full_text = "\n".join(parts)

        if not full_text.strip():
            raise ParsingError(
                "python-docx extracted no text from the DOCX — "
                "the file may be empty or corrupted.",
                source="fallback_docx",
            )

        logger.info(
            "fallback_docx_extraction_complete",
            paragraphs_extracted=len(paragraphs),
            char_count=len(full_text),
        )

        return full_text

    except ParsingError:
        raise
    except Exception as e:
        logger.error("fallback_docx_extraction_failed", exc=str(e))
        raise ParsingError(
            f"python-docx fallback failed: {e}",
            source="fallback_docx",
        ) from e
