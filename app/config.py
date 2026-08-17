from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Uygulama ayarları. Ortam değişkenlerinden okunur."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Veritabanı
    database_url: str = "postgresql+psycopg2://iha:iha@localhost:5432/iha_filo"

    # Mesaj kuyruğu (Celery + RabbitMQ) — sonraki fazlarda kullanılacak
    celery_broker_url: str = "amqp://guest:guest@localhost:5672//"
    celery_result_backend: str = "rpc://"

    # Güvenlik — JWT (sonraki fazlarda kullanılacak)
    secret_key: str = "degistir-beni-cok-gizli-anahtar"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Genel
    app_name: str = "IHA Filo Telemetri ve Gorev Yonetim Sistemi"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
