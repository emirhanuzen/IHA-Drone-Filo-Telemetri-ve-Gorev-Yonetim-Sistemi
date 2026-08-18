from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Tüm ORM modellerinin türeyeceği taban sınıf."""

    pass


def get_db() -> Generator:
    """FastAPI bağımlılığı: her istek için bir veritabanı oturumu açar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator:
    """FastAPI dışında (Celery worker'ında) kullanılan oturum yöneticisi.

    Hata durumunda rollback yapar, her hâlükârda oturumu kapatır.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
