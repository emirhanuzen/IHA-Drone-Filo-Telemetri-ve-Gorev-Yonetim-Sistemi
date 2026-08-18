"""Sensör uyarısı (SensorAlert) iş mantığı.

Uyarılar iki yoldan doğar:
  * Otomatik — worker, her telemetri kaydını işlerken kuralları uygular.
  * Elle    — operatör, sinyal kaybı gibi bir durumu kendisi bildirir.

Kurallar:
  * Yakıt %15'in altındaysa "düşük yakıt" uyarısı üretilir.
  * İki ölçüm arasındaki konum farkı, geçen sürede fiziksel olarak kat
    edilemeyecek kadar büyükse "anomali" uyarısı üretilir.
"""

import math
from collections import defaultdict

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events import publish_events
from app.models.alert import SensorAlert
from app.models.enums import AlertSeverity, AlertType
from app.models.telemetry import TelemetryLog
from app.schemas.alert import SensorAlertCreate
from app.services import drone as drone_service

# Her uyarı oluştuğunda RabbitMQ'ya basılan event'in routing key'i.
ALERT_CREATED_EVENT = "alert.created"

# Bu yüzdenin altındaki yakıt seviyesi uyarı üretir.
LOW_FUEL_THRESHOLD = 15.0

# Yakıtın "kritik" sayıldığı seviye.
CRITICAL_FUEL_THRESHOLD = 5.0

# Bir İHA için makul kabul edilen azami yatay hız (km/s). Bunun üzerindeki
# örtük hız, konum sıçraması (anomali) sayılır.
MAX_PLAUSIBLE_SPEED_KMH = 400.0

# Aynı zaman damgasına sahip iki ölçüm arasında tolere edilen mesafe (km).
MAX_JUMP_DISTANCE_KM = 1.0

DUNYA_YARICAPI_KM = 6371.0


def get_alert(db: Session, alert_id: int) -> SensorAlert:
    """Tek bir uyarıyı getirir; bulunamazsa 404 döner."""
    alert = db.get(SensorAlert, alert_id)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Uyari bulunamadi"
        )
    return alert


def list_alerts(
    db: Session,
    drone_id: int | None = None,
    alert_type: AlertType | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[SensorAlert]:
    """Uyarıları listeler; drone ve tipe göre filtrelenebilir."""
    stmt = select(SensorAlert)
    if drone_id is not None:
        stmt = stmt.where(SensorAlert.drone_id == drone_id)
    if alert_type is not None:
        stmt = stmt.where(SensorAlert.alert_type == alert_type)
    stmt = stmt.offset(skip).limit(limit).order_by(SensorAlert.timestamp.desc())
    return list(db.scalars(stmt).all())


def build_event_payload(alert: SensorAlert) -> dict:
    """Uyarıyı event gövdesine dönüştürür.

    Payload, oturum commit edilmeden ÖNCE hazırlanır; commit sonrası nesne
    alanları tazelenmek zorunda kalmasın diye.
    """
    return {
        "event": ALERT_CREATED_EVENT,
        "alert_id": alert.id,
        "drone_id": alert.drone_id,
        "telemetry_log_id": alert.telemetry_log_id,
        "alert_type": alert.alert_type.value,
        "severity": alert.severity.value,
        "message": alert.message,
        "timestamp": alert.timestamp.isoformat(),
    }


def publish_alert_created(payloads: list[dict]) -> None:
    """Hazırlanmış uyarı event'lerini "alert.created" ile yayınlar."""
    publish_events(ALERT_CREATED_EVENT, payloads)


def create_alert(db: Session, data: SensorAlertCreate) -> SensorAlert:
    """Elle bir uyarı kaydı oluşturur ve event'ini yayınlar."""
    drone_service.get_drone(db, data.drone_id)

    alert = SensorAlert(**data.model_dump(exclude_none=True))
    db.add(alert)
    db.flush()
    payload = build_event_payload(alert)
    db.commit()

    # Event, kayıt kalıcı olduktan SONRA yayınlanır.
    publish_alert_created([payload])
    db.refresh(alert)
    return alert


# ---------------------------------------------------------------------------
# Otomatik uyarı üretimi (worker tarafı)
# ---------------------------------------------------------------------------


def _haversine_km(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """İki koordinat arasındaki büyük daire mesafesini km olarak döner."""
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return 2 * DUNYA_YARICAPI_KM * math.asin(math.sqrt(a))


def _check_low_fuel(log: TelemetryLog) -> SensorAlert | None:
    """Yakıt eşiğin altındaysa düşük yakıt uyarısı üretir."""
    if log.fuel_percentage >= LOW_FUEL_THRESHOLD:
        return None

    severity = (
        AlertSeverity.KRITIK
        if log.fuel_percentage < CRITICAL_FUEL_THRESHOLD
        else AlertSeverity.YUKSEK
    )
    return SensorAlert(
        drone_id=log.drone_id,
        telemetry_log_id=log.id,
        timestamp=log.timestamp,
        alert_type=AlertType.DUSUK_YAKIT,
        severity=severity,
        message=f"Yakit seviyesi %{log.fuel_percentage:.1f} seviyesine dustu",
    )


def _check_position_jump(
    log: TelemetryLog, previous: TelemetryLog | None
) -> SensorAlert | None:
    """Bir önceki ölçüme göre beklenmedik konum sıçraması var mı bakar."""
    if previous is None:
        return None

    distance_km = _haversine_km(
        previous.latitude, previous.longitude, log.latitude, log.longitude
    )
    elapsed_hours = (log.timestamp - previous.timestamp).total_seconds() / 3600

    if elapsed_hours <= 0:
        # Zaman ilerlememiş: küçük bir sapma ölçüm gürültüsü sayılır.
        if distance_km <= MAX_JUMP_DISTANCE_KM:
            return None
        implied_speed = float("inf")
    else:
        implied_speed = distance_km / elapsed_hours
        if implied_speed <= MAX_PLAUSIBLE_SPEED_KMH:
            return None

    speed_text = (
        "olcum ayni anda" if math.isinf(implied_speed) else f"{implied_speed:.0f} km/s"
    )
    return SensorAlert(
        drone_id=log.drone_id,
        telemetry_log_id=log.id,
        timestamp=log.timestamp,
        alert_type=AlertType.ANOMALI,
        severity=AlertSeverity.YUKSEK,
        message=(
            f"Beklenmedik konum sicramasi: {distance_km:.1f} km ({speed_text})"
        ),
    )


def _previous_log(db: Session, drone_id: int, before_id: int) -> TelemetryLog | None:
    """Drone'un, verilen kayıttan önceki son telemetri kaydını getirir."""
    stmt = (
        select(TelemetryLog)
        .where(TelemetryLog.drone_id == drone_id, TelemetryLog.id < before_id)
        .order_by(TelemetryLog.timestamp.desc(), TelemetryLog.id.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def evaluate_logs(db: Session, logs: list[TelemetryLog]) -> list[SensorAlert]:
    """Yeni yazılmış telemetri kayıtlarını kurallardan geçirip uyarı üretir.

    Kayıtlar drone bazında gruplanır ve zaman sırasına dizilir; her drone için
    veritabanındaki son ölçüm bir kez okunur, sonrası paket içinde ilerler.

    Uyarılar oturuma eklenip flush edilir; COMMIT çağıranın sorumluluğunda,
    böylece telemetri kayıtları ile uyarılar aynı işlemde kalıcı olur.
    """
    if not logs:
        return []

    by_drone: dict[int, list[TelemetryLog]] = defaultdict(list)
    for log in logs:
        by_drone[log.drone_id].append(log)

    alerts: list[SensorAlert] = []
    for drone_id, drone_logs in by_drone.items():
        drone_logs.sort(key=lambda item: (item.timestamp, item.id))
        previous = _previous_log(db, drone_id, before_id=drone_logs[0].id)

        for log in drone_logs:
            for alert in (_check_low_fuel(log), _check_position_jump(log, previous)):
                if alert is not None:
                    alerts.append(alert)
            previous = log

    if alerts:
        db.add_all(alerts)
        db.flush()

    return alerts
