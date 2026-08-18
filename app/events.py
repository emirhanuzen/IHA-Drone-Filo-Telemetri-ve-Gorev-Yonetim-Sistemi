"""RabbitMQ üzerinden event yayınlama.

Celery'nin kuyruğundan bağımsız olarak, sistemde olup biteni dinlemek isteyen
başka servisler için bir topic exchange'e event basılır. Yayın başarısız olursa
asıl iş (uyarının veritabanına yazılması) düşmez; yalnızca log'a yazılır.
"""

import logging

from kombu import Connection, Exchange

from app.config import settings

logger = logging.getLogger(__name__)

events_exchange = Exchange(settings.events_exchange, type="topic", durable=True)

# Bağlantı kurulamazsa sonsuza kadar beklenmesin.
_RETRY_POLICY = {"interval_start": 0, "interval_step": 0.5, "max_retries": 3}


def publish_event(routing_key: str, payload: dict) -> bool:
    """Verilen event'i exchange'e yayınlar; başarılıysa True döner."""
    try:
        with Connection(
            settings.celery_broker_url, connect_timeout=5
        ) as connection:
            producer = connection.Producer(serializer="json")
            producer.publish(
                payload,
                exchange=events_exchange,
                routing_key=routing_key,
                declare=[events_exchange],
                retry=True,
                retry_policy=_RETRY_POLICY,
            )
    except Exception:
        logger.exception("Event yayinlanamadi: %s", routing_key)
        return False

    logger.info("Event yayinlandi: %s", routing_key)
    return True
