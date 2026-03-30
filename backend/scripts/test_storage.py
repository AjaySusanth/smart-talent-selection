from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.services.storage import delete_file, get_presigned_url, upload_file


async def main() -> None:
    key = (
        f"manual-test/storage-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.txt"
    )
    content = b"storage smoke test"

    uploaded_key = await upload_file(content, key, "text/plain")
    signed_url = await get_presigned_url(uploaded_key, expiry_seconds=300)
    await delete_file(uploaded_key)

    print(f"Uploaded key: {uploaded_key}")
    print(f"Signed URL: {signed_url}")
    print("Deleted key successfully")


if __name__ == "__main__":
    asyncio.run(main())
