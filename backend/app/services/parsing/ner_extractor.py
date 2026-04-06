"""
Named Entity Recognition (NER) via HuggingFace Inference API.

Task 3.3 — Identifies Person Names, Organizations, and Locations
from resume text using the dslim/bert-base-NER model hosted on
HuggingFace's serverless Inference API.

These entities are passed as "hints" to the Gemini LLM step (Task 3.4)
to improve structured extraction accuracy and reduce hallucination.

Design decisions:
  - Uses HF Inference API (not local model) to avoid Docker bloat
  - Chunks text at ~1500 chars to stay within model token limits
  - Merges B-*/I-* subword tokens into complete entity strings
  - Deduplicates entities while preserving first-occurrence order
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

# HuggingFace Inference API endpoint for NER
_HF_NER_MODEL = "dslim/bert-base-NER"
_HF_API_URL = f"https://router.huggingface.co/hf-inference/models/{_HF_NER_MODEL}"

# Maximum characters per API call (~512 tokens ≈ 1500 chars for English)
_MAX_CHUNK_CHARS = 1500

# Entity type mapping from BERT NER labels to our domain
_ENTITY_MAP = {
    "PER": "names",
    "ORG": "organizations",
    "LOC": "locations",
}


@dataclass
class NERResult:
    """Container for named entities extracted from resume text."""

    names: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to a plain dict for JSON serialisation and logging."""
        return {
            "names": self.names,
            "organizations": self.organizations,
            "locations": self.locations,
        }


def _chunk_text(text: str, max_chars: int = _MAX_CHUNK_CHARS) -> list[str]:
    """
    Split text into chunks that fit within the model's token limit.

    Splits on sentence boundaries ('. ') when possible to avoid
    cutting entities in half. Falls back to hard truncation.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        # Try to split at a sentence boundary
        split_pos = remaining[:max_chars].rfind(". ")
        if split_pos == -1 or split_pos < max_chars // 2:
            # No good sentence boundary — split at newline or hard truncate
            split_pos = remaining[:max_chars].rfind("\n")
            if split_pos == -1 or split_pos < max_chars // 2:
                split_pos = max_chars

        chunks.append(remaining[:split_pos + 1])
        remaining = remaining[split_pos + 1:]

    return chunks


def _merge_entities(api_response: list[dict]) -> dict[str, list[str]]:
    """
    Merge consecutive subword tokens into complete entity strings.

    The HF router returns individual tokens with position data:
      [
        {"entity_group": "PER", "word": "A",     "start": 11, "end": 12, "score": 0.99},
        {"entity_group": "PER", "word": "##jay", "start": 12, "end": 15, "score": 0.99},
      ]

    We merge consecutive tokens of the same entity type into a single
    entity string: "Ajay". Uses start/end positions to detect adjacency.
    """
    if not api_response:
        return {"names": [], "organizations": [], "locations": []}

    # Step 1: Merge consecutive tokens into entity spans
    merged_spans: list[dict] = []

    for token in api_response:
        # Support both "entity_group" and "entity" field names
        entity_type = token.get("entity_group") or token.get("entity", "")

        # Strip B-/I- prefix if the API returns raw labels
        if entity_type.startswith(("B-", "I-")):
            entity_type = entity_type[2:]

        field_name = _ENTITY_MAP.get(entity_type)
        if not field_name:
            continue  # Skip MISC and unknown types

        word = token.get("word", "")
        score = token.get("score", 0)
        start = token.get("start", -1)
        end = token.get("end", -1)

        if score < 0.7:
            continue

        # Check if this token continues the previous entity
        if (
            merged_spans
            and merged_spans[-1]["field"] == field_name
            and start <= merged_spans[-1]["end"] + 1  # adjacent or overlapping
        ):
            # Append to the current span
            prev = merged_spans[-1]
            if word.startswith("##"):
                prev["text"] += word[2:]  # remove ## and concatenate directly
            else:
                prev["text"] += " " + word  # separate word, add space
            prev["end"] = end
            prev["score"] = min(prev["score"], score)
        else:
            # Start a new entity span
            clean_word = word[2:] if word.startswith("##") else word
            merged_spans.append({
                "field": field_name,
                "text": clean_word,
                "start": start,
                "end": end,
                "score": score,
            })

    # Step 2: Group by field and deduplicate
    grouped: dict[str, list[str]] = {
        "names": [],
        "organizations": [],
        "locations": [],
    }
    seen: dict[str, set[str]] = {
        "names": set(),
        "organizations": set(),
        "locations": set(),
    }

    for span in merged_spans:
        text = span["text"].strip()
        if not text or len(text) < 2:
            continue

        field_name = span["field"]
        text_lower = text.lower()

        if text_lower not in seen[field_name]:
            seen[field_name].add(text_lower)
            grouped[field_name].append(text)

    return grouped


def _call_hf_api(text: str) -> list[dict]:
    """
    Call the HuggingFace Inference API for NER.

    Uses synchronous httpx since this runs in a Celery worker thread.
    Includes retry logic for model cold-start (HTTP 503).
    """
    headers = {
        "Authorization": f"Bearer {settings.hf_api_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": text,
        "parameters": {
            "aggregation_strategy": "simple",
        },
    }

    max_retries = 3
    retry_delay = 5  # seconds — HF cold-start can take 20-30s

    for attempt in range(max_retries):
        try:
            response = httpx.post(
                _HF_API_URL,
                json=payload,
                headers=headers,
                timeout=60.0,
            )

            if response.status_code == 503:
                # Model is loading (cold start) — wait and retry
                estimated_time = response.json().get("estimated_time", retry_delay)
                logger.warning(
                    "hf_model_loading",
                    attempt=attempt + 1,
                    estimated_time=estimated_time,
                )
                import time as _time
                _time.sleep(min(estimated_time, 30))
                continue

            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(
                "hf_api_http_error",
                status_code=e.response.status_code,
                attempt=attempt + 1,
                response_text=e.response.text[:200],
            )
            if attempt == max_retries - 1:
                raise
        except httpx.TimeoutException:
            logger.warning(
                "hf_api_timeout",
                attempt=attempt + 1,
            )
            if attempt == max_retries - 1:
                raise

    return []


def extract_entities(text: str) -> NERResult:
    """
    Extract named entities from resume text using HuggingFace Inference API.

    This function:
      1. Chunks the text to fit within BERT's 512-token limit
      2. Calls the HF API for each chunk
      3. Merges and deduplicates the results

    Args:
        text: Normalised resume text from the text extractor

    Returns:
        NERResult with grouped and deduplicated entities

    Note:
        If the HF API is unavailable, returns an empty NERResult
        and logs a warning. The pipeline continues without NER —
        the LLM step (Task 3.4) can still extract entities, just
        with slightly less accuracy.
    """
    start_time = time.monotonic()
    result = NERResult()

    try:
        chunks = _chunk_text(text)
        logger.info(
            "ner_api_started",
            text_length=len(text),
            chunk_count=len(chunks),
        )

        all_entities: list[dict] = []

        for i, chunk in enumerate(chunks):
            chunk_entities = _call_hf_api(chunk)
            all_entities.extend(chunk_entities)
            logger.debug(
                "ner_chunk_processed",
                chunk_index=i,
                entities_found=len(chunk_entities),
            )

        # Merge and deduplicate
        grouped = _merge_entities(all_entities)
        result.names = grouped["names"]
        result.organizations = grouped["organizations"]
        result.locations = grouped["locations"]

        duration_ms = int((time.monotonic() - start_time) * 1000)
        logger.info(
            "ner_extraction_complete",
            duration_ms=duration_ms,
            names_count=len(result.names),
            orgs_count=len(result.organizations),
            locations_count=len(result.locations),
        )

    except Exception as e:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        logger.warning(
            "ner_extraction_failed_gracefully",
            exc=str(e),
            duration_ms=duration_ms,
            hint="Pipeline continues without NER — LLM will handle entity extraction",
        )
        # Return empty result — NER is a "nice to have" hint, not critical

    return result
