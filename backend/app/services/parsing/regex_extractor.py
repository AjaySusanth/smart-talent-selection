"""
Deterministic field extraction using regular expressions.

Task 3.2 — Extracts contact information and social links from
resume text BEFORE sending to the LLM. This avoids wasting tokens
on easily-parseable structured data.

Extracted fields:
  - Email addresses
  - Phone numbers (international formats)
  - LinkedIn profile URLs
  - GitHub profile URLs
  - Portfolio / personal website URLs
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


# ─── Compiled patterns (evaluated once on module import) ───────────────────

# Email: RFC 5322 simplified — covers 99%+ of real-world addresses
_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
)

# Phone: international formats with optional country code
# Matches: +91-8943460250, +1 (555) 123-4567, 8943460250, (555)123-4567
_PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s\-.]?)?"       # optional country code: +91, +1, etc.
    r"(?:\(?\d{2,4}\)?[\s\-.]?)?"     # optional area code: (555), 89, etc.
    r"\d{3,5}"                         # first group of digits
    r"[\s\-.]?"                        # separator
    r"\d{3,5}"                         # second group of digits
    r"(?:[\s\-.]?\d{1,5})?",          # optional extension
)

# LinkedIn: handles full URLs and shorthand references
_LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/([a-zA-Z0-9\-]+)",
    re.IGNORECASE,
)

# GitHub: handles full URLs and shorthand references
_GITHUB_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9\-]+)",
    re.IGNORECASE,
)

# Portfolio / personal website: common patterns in resumes
# Excludes known social/platform domains to avoid false positives
_EXCLUDED_DOMAINS = {
    "linkedin.com", "github.com", "twitter.com", "x.com",
    "facebook.com", "instagram.com", "youtube.com", "medium.com",
    "stackoverflow.com", "leetcode.com", "hackerrank.com",
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
}

_WEBSITE_RE = re.compile(
    r"https?://(?:www\.)?([a-zA-Z0-9\-]+\.[a-zA-Z]{2,})(?:/[^\s,)]*)?",
    re.IGNORECASE,
)


@dataclass
class RegexResult:
    """Container for all deterministic fields extracted from resume text."""

    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    linkedin_url: str | None = None
    linkedin_handle: str | None = None
    github_url: str | None = None
    github_handle: str | None = None
    portfolio_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to a plain dict for JSON serialisation and logging."""
        return {
            "emails": self.emails,
            "phones": self.phones,
            "linkedin_url": self.linkedin_url,
            "linkedin_handle": self.linkedin_handle,
            "github_url": self.github_url,
            "github_handle": self.github_handle,
            "portfolio_urls": self.portfolio_urls,
        }


def _clean_phone(raw: str) -> str | None:
    """
    Normalise a phone match: strip whitespace, keep only digits and leading +.

    Returns None if the result has fewer than 7 digits (likely a false positive
    like a year or ZIP code).
    """
    digits = re.sub(r"[^\d+]", "", raw)
    # Strip leading + for digit count check
    digit_only = digits.lstrip("+")
    if len(digit_only) < 7 or len(digit_only) > 15:
        return None
    return digits


def extract_deterministic_fields(text: str) -> RegexResult:
    """
    Extract contact information and social links from resume text.

    This function is pure, fast, and deterministic — no API calls,
    no ML models. It should be called immediately after text extraction
    and normalisation (Task 3.1).

    Args:
        text: Normalised resume text from the text extractor

    Returns:
        RegexResult with all discovered fields
    """
    result = RegexResult()

    # ── Emails ──────────────────────────────────────────────────────────
    email_matches = _EMAIL_RE.findall(text)
    # Deduplicate while preserving order
    seen_emails: set[str] = set()
    for email in email_matches:
        email_lower = email.lower()
        if email_lower not in seen_emails:
            seen_emails.add(email_lower)
            result.emails.append(email_lower)

    # ── Phone numbers ───────────────────────────────────────────────────
    phone_matches = _PHONE_RE.findall(text)
    seen_phones: set[str] = set()
    for raw_phone in phone_matches:
        cleaned = _clean_phone(raw_phone)
        if cleaned and cleaned not in seen_phones:
            seen_phones.add(cleaned)
            result.phones.append(cleaned)

    # ── LinkedIn ────────────────────────────────────────────────────────
    linkedin_match = _LINKEDIN_RE.search(text)
    if linkedin_match:
        handle = linkedin_match.group(1)
        result.linkedin_handle = handle
        result.linkedin_url = f"https://linkedin.com/in/{handle}"

    # ── GitHub ──────────────────────────────────────────────────────────
    github_match = _GITHUB_RE.search(text)
    if github_match:
        handle = github_match.group(1)
        result.github_handle = handle
        result.github_url = f"https://github.com/{handle}"

    # ── Portfolio / personal websites ───────────────────────────────────
    website_matches = _WEBSITE_RE.finditer(text)
    seen_urls: set[str] = set()
    for match in website_matches:
        domain = match.group(1).lower()
        full_url = match.group(0)

        # Skip known social/platform domains
        if any(domain.endswith(excluded) for excluded in _EXCLUDED_DOMAINS):
            continue

        if full_url not in seen_urls:
            seen_urls.add(full_url)
            result.portfolio_urls.append(full_url)

    logger.info(
        "regex_extraction_complete",
        emails_found=len(result.emails),
        phones_found=len(result.phones),
        has_linkedin=result.linkedin_url is not None,
        has_github=result.github_url is not None,
        portfolio_count=len(result.portfolio_urls),
    )

    return result
