"""Celery uygulaması.

Broker ve sonuç arka ucu RabbitMQ üzerinden çalışır. Task modülleri `include`
ile kaydedilir; worker şu komutla ayağa kalkar:

    celery -A app.celery_app.celery_app worker --loglevel=info
"""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "iha_filo",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.telemetry"],
)

celery_app.conf.update(
    task_default_queue=settings.celery_task_queue,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Worker bir görevi ancak bitirdikten sonra onaylasın; çökme hâlinde
    # telemetri paketi kaybolmasın.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
)
