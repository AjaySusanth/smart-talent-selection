from __future__ import annotations

import asyncio
from collections.abc import Mapping

from supabase import Client, create_client

from app.core.config import settings


def get_supabase_client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_key)


async def upload_file(file_bytes: bytes, key: str, mime_type: str) -> str:
    """Upload bytes to Supabase Storage and return stored object key."""

    def _upload() -> None:
        client = get_supabase_client()
        client.storage.from_(settings.supabase_storage_bucket).upload(
            key,
            file_bytes,
            file_options={"content-type": mime_type, "upsert": "true"},
        )

    await asyncio.to_thread(_upload)
    return key


async def get_presigned_url(key: str, expiry_seconds: int = 3600) -> str:
    """Create a signed URL for an object key."""

    def _create_signed_url():
        client = get_supabase_client()
        return client.storage.from_(settings.supabase_storage_bucket).create_signed_url(
            key,
            expiry_seconds,
        )

    result = await asyncio.to_thread(_create_signed_url)

    if isinstance(result, str):
        return result

    if isinstance(result, Mapping):
        for candidate_key in ("signedURL", "signedUrl"):
            value = result.get(candidate_key)
            if isinstance(value, str) and value:
                return value

        data = result.get("data")
        if isinstance(data, Mapping):
            for candidate_key in ("signedURL", "signedUrl"):
                value = data.get(candidate_key)
                if isinstance(value, str) and value:
                    return value

    raise ValueError(f"Unable to parse signed URL response: {result!r}")


async def delete_file(key: str) -> None:
    """Delete an object key from Supabase Storage."""

    def _delete() -> None:
        client = get_supabase_client()
        client.storage.from_(settings.supabase_storage_bucket).remove([key])

    await asyncio.to_thread(_delete)
