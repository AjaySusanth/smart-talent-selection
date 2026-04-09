"""Azure OpenAI embedding generator for parsed candidate profiles."""

from __future__ import annotations

from functools import lru_cache

import structlog
from openai import AzureOpenAI

from app.core.config import settings

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def _client() -> AzureOpenAI:
    if not settings.azure_openai_endpoint or not settings.azure_openai_key:
        raise ValueError(
            "Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY."
        )

    return AzureOpenAI(
        api_key=settings.azure_openai_key,
        api_version=settings.azure_openai_api_version,
        azure_endpoint=settings.azure_openai_endpoint,
    )


def generate_embedding(text: str) -> list[float]:
    """Generate a 1536-dim embedding vector from structured candidate text."""
    if not text or not text.strip():
        raise ValueError("Cannot generate embedding from empty text")

    logger.info(
        "embedding_generation_started",
        provider="azure_openai",
        deployment=settings.azure_openai_embedding_deployment,
        input_chars=len(text),
    )

    response = _client().embeddings.create(
        model=settings.azure_openai_embedding_deployment,
        input=text,
    )

    if not response.data or not response.data[0].embedding:
        raise ValueError("Azure OpenAI returned empty embedding response")

    vector = response.data[0].embedding
    if len(vector) != settings.embedding_dimension:
        raise ValueError(
            f"Expected embedding dimension {settings.embedding_dimension}, got {len(vector)}"
        )

    logger.info(
        "embedding_generation_complete",
        provider="azure_openai",
        deployment=settings.azure_openai_embedding_deployment,
        dimensions=len(vector),
        tokens_used=response.usage.total_tokens if response.usage else None,
    )

    return vector
