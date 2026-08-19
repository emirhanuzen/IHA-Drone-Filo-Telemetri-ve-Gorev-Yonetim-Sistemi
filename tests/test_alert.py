"""Sensör uyarısı testleri: otomatik üretim kuralları ve event yayınlama.

Uyarılar iki kuraldan doğar:
  * Yakıt %15'in altına düşerse -> düşük yakıt uyarısı
  * İki ölçüm arasında fiziksel olarak imkânsız bir konum sıçraması varsa
    -> anomali uyarısı

Her uyarı için RabbitMQ'ya "alert.created" event'i basılmalıdır; testlerde
yayıncı sahte bir fonksiyonla değiştirildiği için ne basıldığı doğrulanabilir.
"""

import pytest

from app.models.alert import SensorAlert
from app.models.enums import AlertSeverity, AlertType
from app.services import alert as alert_service
from app.services import telemetry as telemetry_service
from tests.conftest import zaman


def kayit(drone_id, dakika=0, **alanlar):
    """Kural testleri için tek bir telemetri sözlüğü üretir."""
    govde = {
        "drone_id": drone_id,
        "latitude": 41.0,
        "longitude": 29.0,
        "altitude": 1000.0,
        "fuel_percentage": 80.0,
        "speed": 120.0,
        "timestamp": zaman(dakika).isoformat(),
    }
    govde.update(alanlar)
    return govde


# ---------------------------------------------------------------------------
# Kural: düşük yakıt
# ---------------------------------------------------------------------------


def test_dusuk_yakit_uyarisi_uretilir(db_session, drone):
    ozet = telemetry_service.save_telemetry_batch(
        db_session, [kayit(drone.id, fuel_percentage=12.0)]
    )

    assert ozet["alerts"] == 1
    uyari = db_session.query(SensorAlert).one()
    assert uyari.alert_type is AlertType.DUSUK_YAKIT
    assert uyari.severity is AlertSeverity.YUKSEK
    assert uyari.drone_id == drone.id


def test_kritik_yakit_seviyesi_kritik_onem_alir(db_session, drone):
    telemetry_service.save_telemetry_batch(
        db_session, [kayit(drone.id, fuel_percentage=3.0)]
    )

    uyari = db_session.query(SensorAlert).one()
    assert uyari.severity is AlertSeverity.KRITIK


@pytest.mark.parametrize("yakit", [15.0, 20.0, 100.0])
def test_yeterli_yakitta_uyari_uretilmez(db_session, drone, yakit):
    ozet = telemetry_service.save_telemetry_batch(
        db_session, [kayit(drone.id, fuel_percentage=yakit)]
    )

    assert ozet["alerts"] == 0
    assert db_session.query(SensorAlert).count() == 0


def test_uyari_kaynak_telemetri_kaydina_baglanir(db_session, drone):
    telemetry_service.save_telemetry_batch(
        db_session, [kayit(drone.id, fuel_percentage=9.0)]
    )

    uyari = db_session.query(SensorAlert).one()
    assert uyari.telemetry_log_id is not None


# ---------------------------------------------------------------------------
# Kural: konum sıçraması (anomali)
# ---------------------------------------------------------------------------


def test_konum_sicramasi_anomali_uyarisi_uretir(db_session, drone):
    """10 dakikada ~111 km -> yaklaşık 667 km/s; bir İHA için imkânsız."""
    ozet = telemetry_service.save_telemetry_batch(
        db_session,
        [
            kayit(drone.id, dakika=0, latitude=41.0),
            kayit(drone.id, dakika=10, latitude=42.0),
        ],
    )

    assert ozet["alerts"] == 1
    uyari = db_session.query(SensorAlert).one()
    assert uyari.alert_type is AlertType.ANOMALI


def test_makul_hareket_anomali_uretmez(db_session, drone):
    """10 dakikada ~11 km -> yaklaşık 66 km/s; normal seyir."""
    ozet = telemetry_service.save_telemetry_batch(
        db_session,
        [
            kayit(drone.id, dakika=0, latitude=41.0),
            kayit(drone.id, dakika=10, latitude=41.1),
        ],
    )

    assert ozet["alerts"] == 0


def test_ilk_kayit_icin_anomali_bakilmaz(db_session, drone):
    """Karşılaştırılacak önceki ölçüm yoksa anomali kararı verilemez."""
    ozet = telemetry_service.save_telemetry_batch(
        db_session, [kayit(drone.id, latitude=41.0, longitude=29.0)]
    )

    assert ozet["alerts"] == 0


def test_ayni_anda_gelen_uzak_olcum_anomali_sayilir(db_session, drone):
    ozet = telemetry_service.save_telemetry_batch(
        db_session,
        [
            kayit(drone.id, dakika=0, latitude=41.0),
            kayit(drone.id, dakika=0, latitude=41.5),
        ],
    )

    assert ozet["alerts"] == 1
    assert db_session.query(SensorAlert).one().alert_type is AlertType.ANOMALI


def test_onceki_paketteki_kayit_da_karsilastirmaya_girer(db_session, drone):
    """Sıçrama, iki ayrı paket arasında da yakalanmalı."""
    telemetry_service.save_telemetry_batch(
        db_session, [kayit(drone.id, dakika=0, latitude=41.0)]
    )

    ozet = telemetry_service.save_telemetry_batch(
        db_session, [kayit(drone.id, dakika=5, latitude=43.0)]
    )

    assert ozet["alerts"] == 1


def test_farkli_drone_lar_birbirini_etkilemez(db_session, drone_factory):
    """Bir drone'un konumu, başka bir drone için sıçrama sayılmamalı."""
    birinci = drone_factory()
    ikinci = drone_factory()

    ozet = telemetry_service.save_telemetry_batch(
        db_session,
        [
            kayit(birinci.id, dakika=0, latitude=41.0),
            kayit(ikinci.id, dakika=1, latitude=48.0),
        ],
    )

    assert ozet["alerts"] == 0


def test_ayni_kayit_hem_yakit_hem_anomali_uyarisi_uretebilir(db_session, drone):
    ozet = telemetry_service.save_telemetry_batch(
        db_session,
        [
            kayit(drone.id, dakika=0, latitude=41.0, fuel_percentage=50.0),
            kayit(drone.id, dakika=5, latitude=43.0, fuel_percentage=8.0),
        ],
    )

    assert ozet["alerts"] == 2
    tipler = {uyari.alert_type for uyari in db_session.query(SensorAlert).all()}
    assert tipler == {AlertType.DUSUK_YAKIT, AlertType.ANOMALI}


# ---------------------------------------------------------------------------
# Event yayınlama
# ---------------------------------------------------------------------------


def test_uyari_olusunca_event_yayinlanir(db_session, drone, published_events):
    telemetry_service.save_telemetry_batch(
        db_session, [kayit(drone.id, fuel_percentage=4.0)]
    )

    assert len(published_events) == 1
    olay = published_events[0]
    assert olay["routing_key"] == alert_service.ALERT_CREATED_EVENT
    govde = olay["payload"]
    assert govde["event"] == "alert.created"
    assert govde["drone_id"] == drone.id
    assert govde["alert_type"] == AlertType.DUSUK_YAKIT.value
    assert govde["severity"] == AlertSeverity.KRITIK.value
    assert govde["alert_id"] is not None


def test_uyari_yoksa_event_yayinlanmaz(db_session, drone, published_events):
    telemetry_service.save_telemetry_batch(
        db_session, [kayit(drone.id, fuel_percentage=75.0)]
    )

    assert published_events == []


def test_her_uyari_icin_ayri_event_basilir(db_session, drone_factory, published_events):
    birinci = drone_factory()
    ikinci = drone_factory()

    telemetry_service.save_telemetry_batch(
        db_session,
        [
            kayit(birinci.id, fuel_percentage=10.0),
            kayit(ikinci.id, fuel_percentage=2.0),
        ],
    )

    assert len(published_events) == 2


def test_event_yayinlanamazsa_uyari_yine_de_kalici_olur(db_session, drone, monkeypatch):
    """RabbitMQ erişilemezse asıl iş düşmemeli; yalnızca event kaybolur."""

    def patlayan_publish(routing_key, payloads):
        raise RuntimeError("broker yok")

    monkeypatch.setattr(alert_service, "publish_events", patlayan_publish)

    with pytest.raises(RuntimeError):
        telemetry_service.save_telemetry_batch(
            db_session, [kayit(drone.id, fuel_percentage=5.0)]
        )

    # Uyarı, event yayınından ÖNCE commit edildiği için veritabanında durmalı.
    assert db_session.query(SensorAlert).count() == 1


# ---------------------------------------------------------------------------
# Elle uyarı ve okuma uçları
# ---------------------------------------------------------------------------


def test_elle_uyari_olusturulur(client, operator_headers, drone, published_events):
    response = client.post(
        "/alerts",
        json={
            "drone_id": drone.id,
            "alert_type": AlertType.SINYAL_KAYBI.value,
            "severity": AlertSeverity.YUKSEK.value,
            "message": "Telsiz baglantisi koptu",
        },
        headers=operator_headers,
    )

    assert response.status_code == 201
    assert response.json()["alert_type"] == AlertType.SINYAL_KAYBI.value
    assert len(published_events) == 1


def test_olmayan_drone_icin_elle_uyari_acilmaz(client, operator_headers):
    response = client.post(
        "/alerts",
        json={
            "drone_id": 9999,
            "alert_type": AlertType.ANOMALI.value,
            "message": "test",
        },
        headers=operator_headers,
    )

    assert response.status_code == 404


def test_uyarilar_listelenir(client, analyst_headers, db_session, drone):
    telemetry_service.save_telemetry_batch(
        db_session,
        [
            kayit(drone.id, dakika=0, fuel_percentage=10.0),
            kayit(drone.id, dakika=1, fuel_percentage=8.0),
        ],
    )

    response = client.get("/alerts", headers=analyst_headers)

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_uyarilar_tipe_gore_filtrelenir(client, analyst_headers, db_session, drone):
    telemetry_service.save_telemetry_batch(
        db_session,
        [
            kayit(drone.id, dakika=0, latitude=41.0, fuel_percentage=50.0),
            kayit(drone.id, dakika=5, latitude=43.0, fuel_percentage=8.0),
        ],
    )

    response = client.get(
        f"/alerts?alert_type={AlertType.ANOMALI.value}", headers=analyst_headers
    )

    assert response.status_code == 200
    govde = response.json()
    assert len(govde) == 1
    assert govde[0]["alert_type"] == AlertType.ANOMALI.value


def test_uyarilar_drone_a_gore_filtrelenir(
    client, analyst_headers, db_session, drone_factory
):
    birinci = drone_factory()
    ikinci = drone_factory()
    telemetry_service.save_telemetry_batch(
        db_session,
        [
            kayit(birinci.id, fuel_percentage=10.0),
            kayit(ikinci.id, fuel_percentage=10.0),
        ],
    )

    response = client.get(f"/alerts?drone_id={ikinci.id}", headers=analyst_headers)

    assert response.status_code == 200
    govde = response.json()
    assert len(govde) == 1
    assert govde[0]["drone_id"] == ikinci.id


def test_tek_uyari_getirilir(client, analyst_headers, db_session, drone):
    telemetry_service.save_telemetry_batch(
        db_session, [kayit(drone.id, fuel_percentage=10.0)]
    )
    uyari_id = db_session.query(SensorAlert).one().id

    response = client.get(f"/alerts/{uyari_id}", headers=analyst_headers)

    assert response.status_code == 200
    assert response.json()["id"] == uyari_id


def test_olmayan_uyari_404_doner(client, analyst_headers):
    response = client.get("/alerts/9999", headers=analyst_headers)

    assert response.status_code == 404
