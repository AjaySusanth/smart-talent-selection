"""
Hyperlink extraction from resume files (Task 2.5 helper).

This module extracts authoritative href values from document structure so
URL fields are not inferred from display text alone.
"""

from __future__ import annotations

import io
import re
import zipfile
from urllib.parse import urlparse

import fitz
import structlog

logger = structlog.get_logger(__name__)

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PDF_MIME = "application/pdf"

_URL_RE = re.compile(r"https?://[^\s<>()\]\[\"']+", re.IGNORECASE)
_LINKEDIN_RE = re.compile(
    r"https?://(?:[\w-]+\.)?linkedin\.com/[^\s<>()\]\[\"']+", re.IGNORECASE
)
_GITHUB_RE = re.compile(
    r"https?://(?:[\w-]+\.)?github\.com/[^\s<>()\]\[\"']+", re.IGNORECASE
)


def _clean_url(url: str) -> str:
    return url.strip().rstrip(".,;)")


def _is_github_profile(url: str) -> bool:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    return parsed.netloc.lower().endswith("github.com") and len(parts) == 1


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _extract_docx_hrefs(file_bytes: bytes) -> list[str]:
    hrefs: list[str] = []

    with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
        rel_files = [
            name
            for name in archive.namelist()
            if name.startswith("word/") and name.endswith(".rels")
        ]

        for rel_path in rel_files:
            xml_text = archive.read(rel_path).decode("utf-8", errors="ignore")
            hrefs.extend(_URL_RE.findall(xml_text))

    return [_clean_url(url) for url in hrefs]


def _extract_pdf_hrefs(file_bytes: bytes) -> list[str]:
    hrefs: list[str] = []
    document = fitz.open(stream=file_bytes, filetype="pdf")

    try:
        for page in document:
            links = page.get_links() or []
            for link in links:
                uri = link.get("uri")
                if uri and isinstance(uri, str):
                    hrefs.append(_clean_url(uri))
    finally:
        document.close()

    return hrefs


def extract_hyperlinks(file_bytes: bytes, mime_type: str) -> dict[str, object]:
    """
    Extract LinkedIn/GitHub/project URLs from document structure.

    Returns a stable dict shape even on extraction failures.
    """
    raw_hrefs: list[str] = []

    try:
        if mime_type == _DOCX_MIME:
            raw_hrefs = _extract_docx_hrefs(file_bytes)
        elif mime_type == _PDF_MIME:
            raw_hrefs = _extract_pdf_hrefs(file_bytes)
        else:
            raw_hrefs = []
    except Exception as exc:
        logger.warning("hyperlink_extraction_failed", mime_type=mime_type, exc=str(exc))
        raw_hrefs = []

    raw_hrefs = _dedupe_preserve_order(raw_hrefs)

    linkedin_urls = [_clean_url(url) for url in raw_hrefs if _LINKEDIN_RE.match(url)]
    github_urls = [_clean_url(url) for url in raw_hrefs if _GITHUB_RE.match(url)]

    github_profile = next((url for url in github_urls if _is_github_profile(url)), None)
    project_urls = [
        url
        for url in raw_hrefs
        if url not in linkedin_urls
        and (url not in github_urls or not _is_github_profile(url))
    ]

    result: dict[str, object] = {
        "linkedin_url": linkedin_urls[0] if linkedin_urls else None,
        "github_url": github_profile,
        "project_urls": project_urls,
        "raw_hrefs": raw_hrefs,
    }

    logger.info(
        "hyperlink_extraction_complete",
        mime_type=mime_type,
        total_hrefs=len(raw_hrefs),
        has_linkedin=result["linkedin_url"] is not None,
        has_github=result["github_url"] is not None,
        project_url_count=len(project_urls),
        linkedin_url=result["linkedin_url"],
        github_url=result["github_url"],
        project_urls=project_urls,
        raw_hrefs=raw_hrefs,
    )

    return result
