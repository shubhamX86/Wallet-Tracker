"""Celery app. Ingestion tasks arrive in Phase 4; only a ping task exists now."""
from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery("whale", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_serializer="json", accept_content=["json"], timezone="UTC")


@celery_app.task(name="system.ping")
def ping() -> str:
    return "pong"
