from fastapi import APIRouter
from fastapi.responses import JSONResponse
from redis.asyncio import from_url
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": settings.version}


@router.get("/health/ready", response_model=None)
async def readiness():
    database_status = "ok"
    redis_status = "ok"
    response: dict[str, str] = {"status": "ok", "database": "ok", "redis": "ok"}

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        database_status = "error"

    redis_client = from_url(settings.redis_url, decode_responses=True)
    try:
        await redis_client.ping()
    except Exception:
        redis_status = "error"
    finally:
        await redis_client.aclose()

    if database_status == "error" or redis_status == "error":
        response["status"] = "degraded"
        response["database"] = database_status
        response["redis"] = redis_status
        return JSONResponse(status_code=503, content=response)

    return response
