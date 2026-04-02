"""
Text normalisation for extracted resume text.

Cleans up formatting artifacts from document extraction without
removing any actual content. Applied after Azure DI or fallback
extraction, before passing text to the LLM extraction step.
"""

from __future__ import annotations

import re
import unicodedata

import structlog

logger = structlog.get_logger(__name__)


def normalise(raw_text: str) -> str:
    """
    Clean and normalise extracted resume text.

    Operations (in order):
      1. Fix Unicode encoding artifacts (smart quotes, dashes, etc.)
      2. Normalise whitespace (collapse runs to single space/newline)
      3. Remove null bytes and control characters
      4. Strip leading/trailing whitespace per line
      5. Collapse 3+ consecutive blank lines to 2

    Does NOT remove content — only cleans formatting.

    Args:
        raw_text: Text from Azure DI or fallback extractor

    Returns:
        Cleaned text ready for LLM processing
    """
    if not raw_text:
        return ""

    text = raw_text

    # 1. Normalise Unicode — NFC form (compose characters)
    text = unicodedata.normalize("NFC", text)

    # 2. Replace common encoding artifacts
    replacements = {
        "\u2018": "'",   # left single quote
        "\u2019": "'",   # right single quote
        "\u201c": '"',   # left double quote
        "\u201d": '"',   # right double quote
        "\u2013": "-",   # en dash
        "\u2014": "-",   # em dash
        "\u2026": "...", # ellipsis
        "\u00a0": " ",   # non-breaking space
        "\u200b": "",    # zero-width space
        "\ufeff": "",    # BOM
        "\t": "    ",    # tabs to spaces
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # 3. Remove null bytes and control chars (keep \n and \r)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # 4. Normalise line endings to \n
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 5. Strip trailing whitespace per line
    text = "\n".join(line.rstrip() for line in text.split("\n"))

    # 6. Collapse runs of spaces (within a line) to a single space
    text = re.sub(r"[ ]{2,}", " ", text)

    # 7. Collapse 3+ consecutive blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 8. Strip leading/trailing whitespace from the whole text
    text = text.strip()

    original_len = len(raw_text)
    normalised_len = len(text)

    logger.debug(
        "text_normalised",
        original_chars=original_len,
        normalised_chars=normalised_len,
        reduction_pct=round((1 - normalised_len / original_len) * 100, 1) if original_len else 0,
    )

    return text
