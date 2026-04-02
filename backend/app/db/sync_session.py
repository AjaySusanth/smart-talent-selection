"""
Synchronous database session for Celery workers.

The main app uses asyncpg (async), but Celery workers run in sync
thread pools. Using asyncpg from a new event loop causes
'Future attached to a different loop' errors.

This module provides a plain psycopg2 synchronous engine instead.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# Convert async URL to sync: postgresql+asyncpg:// → postgresql+psycopg2://
_sync_url = settings.database_url.replace(
    "postgresql+asyncpg", "postgresql+psycopg2"
)

sync_engine = create_engine(_sync_url, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(bind=sync_engine)


def get_sync_session() -> Session:
    """Get a synchronous DB session for use in Celery workers."""
    return SyncSessionLocal()
