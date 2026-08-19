"""Telemetri testleri: tekil kayıt, toplu (asenkron) gönderim ve CSV işleme.

Toplu gönderimde API kayıt YAZMAZ; yalnızca doğrulayıp Celery kuyruğuna
bırakır. Bu yüzden testler iki tarafı ayrı ayrı sınar:
  * API tarafı  -> 202 dönüyor mu, kuyruğa doğru görev bırakılıyor mu?
  * Worker tarafı -> aynı paket veritabanına doğru yazılıyor mu?
"""

import pandas as pd
import pytest

from app.models.telemetry import TelemetryLog
from app.services import telemetry as telemetry_service
from tests.conftest import zaman


def test_tekil_telemetri_kaydi_olusturulur(
    client, operator_headers, drone, telemetri_kaydi
):
    response = client.post(
        "/telemetry", json=telemetri_kaydi(drone.id), headers=operator_headers
    )

    assert response.status_code == 201
    govde = response.json()
    assert govde["drone_id"] == drone.id
    assert govde["altitude"] == 1200.0


def test_olmayan_drone_icin_telemetri_reddedilir(
    client, operator_headers, telemetri_kaydi
):
    response = client.post(
        "/telemetry", json=telemetri_kaydi(9999), headers=operator_headers
    )

    assert response.status_code == 404


def test_zaman_damgasi_verilmezse_sunucu_zamani_kullanilir(
    client, operator_headers, drone, telemetri_kaydi
):
    kayit = telemetri_kaydi(drone.id)
    kayit.pop("timestamp")

    response = client.post("/telemetry", json=kayit, headers=operator_headers)

    assert response.status_code == 201
    assert response.json()["timestamp"] is not None


@pytest.mark.parametrize(
    "bozuk_alan",
    [
        {"latitude": 95.0},
        {"longitude": -200.0},
        {"fuel_percentage": 140.0},
        {"speed": -10.0},
    ],
)
def test_gecersiz_telemetri_degerleri_reddedilir(
    client, operator_headers, drone, telemetri_kaydi, bozuk_alan
):
    response = client.post(
        "/telemetry",
        json=telemetri_kaydi(drone.id, **bozuk_alan),
        headers=operator_headers,
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Toplu gönderim: API tarafı (kuyruğa bırakma)
# ---------------------------------------------------------------------------


def test_toplu_gonderim_202_ve_task_id_doner(
    client, operator_headers, drone, telemetri_kaydi, queued_tasks
):
    paket = [telemetri_kaydi(drone.id, fuel_percentage=90.0 - i) for i in range(3)]

    response = client.post("/telemetry/bulk", json=paket, headers=operator_headers)

    assert response.status_code == 202
    govde = response.json()
    assert govde["received"] == 3
    assert govde["status"] == "kuyruga_alindi"
    assert govde["task_id"]
    assert len(queued_tasks) == 1
    assert queued_tasks[0]["name"] == telemetry_service.TASK_PROCESS_BATCH


def test_toplu_gonderim_senkron_yazmaz(
    client, operator_headers, db_session, drone, telemetri_kaydi
):
    """Kayıtlar worker'a bırakılır; istek dönerken veritabanı hâlâ boş olmalı."""
    client.post(
        "/telemetry/bulk", json=[telemetri_kaydi(drone.id)], headers=operator_headers
    )

    assert db_session.query(TelemetryLog).count() == 0


def test_toplu_gonderimde_olmayan_drone_404_doner(
    client, operator_headers, drone, telemetri_kaydi, queued_tasks
):
    paket = [telemetri_kaydi(drone.id), telemetri_kaydi(9999)]

    response = client.post("/telemetry/bulk", json=paket, headers=operator_headers)

    assert response.status_code == 404
    # Hatalı paket kuyruğa hiç bırakılmamalı.
    assert queued_tasks == []


def test_bos_paket_reddedilir(client, operator_headers):
    response = client.post("/telemetry/bulk", json=[], headers=operator_headers)

    assert response.status_code == 422


def test_gorev_durumu_sorgulanir(client, operator_headers, monkeypatch):
    monkeypatch.setattr(
        telemetry_service,
        "get_task_state",
        lambda task_id: {"task_id": task_id, "state": "SUCCESS", "result": {"inserted": 5}},
    )

    response = client.get("/telemetry/tasks/abc-123", headers=operator_headers)

    assert response.status_code == 200
    govde = response.json()
    assert govde["state"] == "SUCCESS"
    assert govde["result"] == {"inserted": 5}


# ---------------------------------------------------------------------------
# Toplu gönderim: worker tarafı (asıl yazma)
# ---------------------------------------------------------------------------


def test_worker_paketi_veritabanina_yazar(db_session, drone, telemetri_kaydi):
    paket = [
        telemetri_kaydi(drone.id, timestamp=zaman(dakika).isoformat())
        for dakika in range(3)
    ]

    ozet = telemetry_service.save_telemetry_batch(db_session, paket)

    assert ozet["received"] == 3
    assert ozet["inserted"] == 3
    assert ozet["skipped"] == 0
    assert db_session.query(TelemetryLog).count() == 3


def test_worker_bozuk_kaydi_atlar_digerlerini_yazar(
    db_session, drone, telemetri_kaydi
):
    """Tek bir bozuk satır yüzünden paketin tamamı düşmemeli."""
    paket = [
        telemetri_kaydi(drone.id),
        {"drone_id": drone.id, "latitude": "kuzey"},
        telemetri_kaydi(drone.id, timestamp=zaman(1).isoformat()),
    ]

    ozet = telemetry_service.save_telemetry_batch(db_session, paket)

    assert ozet["inserted"] == 2
    assert ozet["skipped"] == 1


def test_worker_olmayan_drone_kaydini_atlar(db_session, drone, telemetri_kaydi):
    paket = [telemetri_kaydi(drone.id), telemetri_kaydi(4242)]

    ozet = telemetry_service.save_telemetry_batch(db_session, paket)

    assert ozet["inserted"] == 1
    assert ozet["skipped"] == 1


def test_bos_paket_worker_i_mesgul_etmez(db_session):
    ozet = telemetry_service.save_telemetry_batch(db_session, [])

    assert ozet == {"received": 0, "inserted": 0, "skipped": 0, "alerts": 0}


# ---------------------------------------------------------------------------
# CSV yükleme
# ---------------------------------------------------------------------------


def csv_yaz(path, drone_id, satir_sayisi=12, yakit=80.0):
    """Test için basit bir telemetri CSV'si üretir."""
    satirlar = [
        {
            "drone_id": drone_id,
            "latitude": 41.0 + i * 0.001,
            "longitude": 29.0 + i * 0.001,
            "altitude": 1000 + i,
            "fuel_percentage": yakit,
            "speed": 110.0,
            "timestamp": zaman(i).isoformat(),
        }
        for i in range(satir_sayisi)
    ]
    pd.DataFrame(satirlar).to_csv(path, index=False)
    return path


def test_csv_yuklemesi_kuyruga_birakilir(
    client, operator_headers, tmp_path, drone, queued_tasks
):
    dosya = csv_yaz(tmp_path / "telemetri.csv", drone.id)

    with dosya.open("rb") as f:
        response = client.post(
            "/telemetry/upload-csv",
            files={"file": ("telemetri.csv", f, "text/csv")},
            headers=operator_headers,
        )

    assert response.status_code == 202
    govde = response.json()
    assert govde["filename"] == "telemetri.csv"
    assert govde["task_id"]
    assert queued_tasks[0]["name"] == telemetry_service.TASK_PROCESS_CSV


def test_csv_disinda_dosya_reddedilir(client, operator_headers, tmp_path):
    dosya = tmp_path / "notlar.txt"
    dosya.write_text("bu bir csv degil", encoding="utf-8")

    with dosya.open("rb") as f:
        response = client.post(
            "/telemetry/upload-csv",
            files={"file": ("notlar.txt", f, "text/plain")},
            headers=operator_headers,
        )

    assert response.status_code == 400


def test_csv_parca_parca_okunur_ve_yazilir(db_session, drone, tmp_path, monkeypatch):
    """Dosya tek seferde belleğe alınmaz; chunk sayısı özette görünmeli."""
    monkeypatch.setattr(telemetry_service.settings, "csv_chunk_size", 5)
    dosya = csv_yaz(tmp_path / "buyuk.csv", drone.id, satir_sayisi=12)

    ozet = telemetry_service.import_telemetry_csv(db_session, str(dosya))

    assert ozet["inserted"] == 12
    # 12 satır, 5'erli parçalar hâlinde -> 3 parça.
    assert ozet["chunks"] == 3
    assert db_session.query(TelemetryLog).count() == 12


def test_csv_eksik_sutunla_reddedilir(db_session, drone, tmp_path):
    dosya = tmp_path / "eksik.csv"
    pd.DataFrame([{"drone_id": drone.id, "latitude": 41.0}]).to_csv(dosya, index=False)

    with pytest.raises(ValueError) as hata:
        telemetry_service.import_telemetry_csv(db_session, str(dosya))

    assert "eksik sutunlar" in str(hata.value).lower()


def test_olmayan_csv_dosyasi_hata_verir(db_session):
    with pytest.raises(FileNotFoundError):
        telemetry_service.import_telemetry_csv(db_session, "/yok/boyle/bir/dosya.csv")


def test_csv_deki_olmayan_drone_satirlari_atlanir(db_session, drone, tmp_path):
    dosya = tmp_path / "karisik.csv"
    satirlar = [
        {
            "drone_id": drone_id,
            "latitude": 41.0,
            "longitude": 29.0,
            "altitude": 1000.0,
            "fuel_percentage": 70.0,
            "speed": 100.0,
            "timestamp": zaman(i).isoformat(),
        }
        for i, drone_id in enumerate([drone.id, 9999, drone.id])
    ]
    pd.DataFrame(satirlar).to_csv(dosya, index=False)

    ozet = telemetry_service.import_telemetry_csv(db_session, str(dosya))

    assert ozet["inserted"] == 2
    assert ozet["skipped"] == 1


# ---------------------------------------------------------------------------
# Listeleme / okuma
# ---------------------------------------------------------------------------


def test_telemetri_listelenir(db_session, client, analyst_headers, drone, telemetri_kaydi):
    telemetry_service.save_telemetry_batch(
        db_session,
        [telemetri_kaydi(drone.id, timestamp=zaman(i).isoformat()) for i in range(4)],
    )

    response = client.get("/telemetry", headers=analyst_headers)

    assert response.status_code == 200
    assert len(response.json()) == 4


def test_telemetri_drone_a_gore_filtrelenir(
    db_session, client, analyst_headers, drone_factory, telemetri_kaydi
):
    birinci = drone_factory()
    ikinci = drone_factory()
    telemetry_service.save_telemetry_batch(
        db_session, [telemetri_kaydi(birinci.id), telemetri_kaydi(ikinci.id)]
    )

    response = client.get(f"/telemetry?drone_id={ikinci.id}", headers=analyst_headers)

    assert response.status_code == 200
    govde = response.json()
    assert len(govde) == 1
    assert govde[0]["drone_id"] == ikinci.id


def test_tek_telemetri_kaydi_getirilir(
    client, operator_headers, drone, telemetri_kaydi
):
    kayit_id = client.post(
        "/telemetry", json=telemetri_kaydi(drone.id), headers=operator_headers
    ).json()["id"]

    response = client.get(f"/telemetry/{kayit_id}", headers=operator_headers)

    assert response.status_code == 200
    assert response.json()["id"] == kayit_id


def test_olmayan_telemetri_kaydi_404_doner(client, analyst_headers):
    response = client.get("/telemetry/9999", headers=analyst_headers)

    assert response.status_code == 404
