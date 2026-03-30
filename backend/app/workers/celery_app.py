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
