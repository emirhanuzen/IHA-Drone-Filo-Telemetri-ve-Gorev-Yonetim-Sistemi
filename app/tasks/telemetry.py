"""Telemetri işleme task'ları.

Task'lar yalnızca oturum açıp servis katmanını çağırır; iş mantığı
`app.services.telemetry` içinde durur.
"""

import logging
from pathlib import Path

from app.celery_app import celery_app
from app.db.database import session_scope
from app.services import telemetry as telemetry_service

logger = logging.getLogger(__name__)


@celery_app.task(name="telemetry.process_batch")
def process_telemetry_batch(records: list[dict]) -> dict:
    """Toplu telemetri paketini veritabanına yazar."""
    with session_scope() as db:
        summary = telemetry_service.save_telemetry_batch(db, records)

    logger.info(
        "Telemetri paketi islendi: %s yazildi, %s atlandi",
        summary["inserted"],
        summary["skipped"],
    )
    return summary


@celery_app.task(name="telemetry.process_csv")
def process_telemetry_csv(file_path: str) -> dict:
    """Yüklenen CSV dosyasını parça parça okuyup veritabanına yazar.

    İş bittiğinde geçici dosya silinir; hata hâlinde de dosya bırakılmaz.
    """
    try:
        with session_scope() as db:
            summary = telemetry_service.import_telemetry_csv(db, file_path)
    finally:
        Path(file_path).unlink(missing_ok=True)

    logger.info(
        "CSV islendi (%s parca): %s yazildi, %s atlandi",
        summary["chunks"],
        summary["inserted"],
        summary["skipped"],
    )
    return summary
