from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "talent_engine",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True

# Explicitly include task modules so Celery registers them on startup
celery_app.conf.include = [
    "app.workers.tasks.parse_resume",
]

# Azure DI F0 tier: limit to 1 concurrent task to avoid burst throttle (Watchout 1)
# Remove this when upgrading to S0 tier
if settings.environment == "development":
    celery_app.conf.worker_concurrency = 1
