"""Testler için ortak yapılandırma ve fixture'lar.

Testler ÜRETİM veritabanına dokunmaz. Varsayılan olarak bellek içi bir SQLite
veritabanı kullanılır; tablolar her testin başında sıfırdan kurulur, sonunda
düşürülür. Gerçek PostgreSQL üzerinde koşturmak istenirse `TEST_DATABASE_URL`
ortam değişkeni verilir (ör. ayrı bir `iha_filo_test` veritabanı):

    TEST_DATABASE_URL=postgresql+psycopg2://iha:iha@postgres:5432/iha_filo_test

Dış servisler (RabbitMQ, Celery worker) testlerde ayağa kaldırılmaz: event
yayınlama ve kuyruğa görev bırakma sahte fonksiyonlarla değiştirilir, böylece
testler tek başına çalışır ve ne yayınlandığı da doğrulanabilir.
"""

import itertools
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.enums import DroneStatus, UserRole
from app.schemas.drone import DroneCreate
from app.security import create_access_token
from app.services import drone as drone_service
from app.services import telemetry as telemetry_service

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


def _create_test_engine():
    """Test motorunu kurar; SQLite'ta tek bağlantı paylaşılır."""
    if TEST_DATABASE_URL.startswith("sqlite"):
        # Bellek içi veritabanı: tüm oturumlar AYNI bağlantıyı kullanmalı,
        # yoksa her oturum boş bir veritabanı görür.
        return create_engine(
            TEST_DATABASE_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(TEST_DATABASE_URL, pool_pre_ping=True)


engine = _create_test_engine()
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    """Her test için temiz bir şema ve veritabanı oturumu."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    """`get_db` bağımlılığı test oturumuyla değiştirilmiş HTTP istemcisi."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def published_events(monkeypatch):
    """RabbitMQ'ya gitmek yerine yayınlanan event'leri toplayan sahte yayıncı."""
    kayitlar: list[dict] = []

    def sahte_publish(routing_key: str, payloads: list[dict]) -> bool:
        for payload in payloads:
            kayitlar.append({"routing_key": routing_key, "payload": payload})
        return True

    monkeypatch.setattr("app.services.alert.publish_events", sahte_publish)
    return kayitlar


@pytest.fixture(autouse=True)
def queued_tasks(monkeypatch):
    """Celery'ye gitmek yerine kuyruğa bırakılan görevleri toplayan sahte gönderici."""
    kayitlar: list[dict] = []

    class SahteSonuc:
        def __init__(self, task_id: str) -> None:
            self.id = task_id

    def sahte_send_task(name, args=None, **kwargs):
        kayitlar.append({"name": name, "args": list(args or [])})
        return SahteSonuc(f"test-task-{len(kayitlar)}")

    monkeypatch.setattr(telemetry_service.celery_app, "send_task", sahte_send_task)
    return kayitlar


@pytest.fixture
def auth_headers():
    """İstenen roldeki bir kullanıcı için Authorization başlığı üretir.

    Token payload'ı kendi kendine yeterli olduğu için kullanıcıyı veritabanına
    yazmaya gerek yoktur — yetki kontrolü zaten veritabanına gitmez.
    """
    sayac = itertools.count(1)

    def _headers(role: UserRole = UserRole.ADMIN, username: str | None = None) -> dict:
        user_id = next(sayac)
        token = create_access_token(
            user_id=user_id,
            username=username or f"{role.value}_{user_id}",
            role=role,
        )
        return {"Authorization": f"Bearer {token}"}

    return _headers


@pytest.fixture
def admin_headers(auth_headers):
    return auth_headers(UserRole.ADMIN)


@pytest.fixture
def commander_headers(auth_headers):
    return auth_headers(UserRole.COMMANDER)


@pytest.fixture
def operator_headers(auth_headers):
    return auth_headers(UserRole.OPERATOR)


@pytest.fixture
def analyst_headers(auth_headers):
    return auth_headers(UserRole.ANALYST)


@pytest.fixture
def drone_factory(db_session):
    """Test için hızlıca drone üretir."""
    sayac = itertools.count(1)

    def _create(
        fuel_percentage: float = 100.0,
        status: DroneStatus = DroneStatus.AKTIF,
        serial_number: str | None = None,
        model: str = "Test TB2",
    ):
        data = DroneCreate(
            serial_number=serial_number or f"IHA-TEST-{next(sayac):03d}",
            model=model,
            fuel_percentage=fuel_percentage,
            status=status,
        )
        return drone_service.create_drone(db_session, data)

    return _create


@pytest.fixture
def drone(drone_factory):
    return drone_factory()


@pytest.fixture
def telemetri_kaydi():
    """Verilen alanları varsayılanlarla tamamlayan telemetri sözlüğü üretir."""

    def _kayit(drone_id: int, **alanlar) -> dict:
        kayit = {
            "drone_id": drone_id,
            "latitude": 41.0,
            "longitude": 29.0,
            "altitude": 1200.0,
            "fuel_percentage": 80.0,
            "speed": 120.0,
            "timestamp": datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc).isoformat(),
        }
        kayit.update(alanlar)
        return kayit

    return _kayit


def telemetri_yaz(db_session, kayitlar: list[dict]) -> dict:
    """Worker'ın yaptığı işi doğrudan çağırır (kuyruğu atlayarak)."""
    return telemetry_service.save_telemetry_batch(db_session, kayitlar)


def zaman(dakika: int = 0) -> datetime:
    """Testlerde sabit bir başlangıç anına göre zaman damgası üretir."""
    return datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc) + timedelta(minutes=dakika)
