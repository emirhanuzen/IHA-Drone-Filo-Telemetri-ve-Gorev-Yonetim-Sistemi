"""Drone CRUD ve doğrulama testleri."""

from app.models.enums import DroneStatus

YENI_DRONE = {
    "serial_number": "IHA-001",
    "model": "Bayraktar TB2",
    "fuel_percentage": 95.0,
}


def test_drone_olusturulur(client, admin_headers):
    response = client.post("/drones", json=YENI_DRONE, headers=admin_headers)

    assert response.status_code == 201
    govde = response.json()
    assert govde["serial_number"] == "IHA-001"
    assert govde["status"] == "aktif"
    assert govde["fuel_percentage"] == 95.0
    assert govde["id"] > 0


def test_ayni_seri_numarasi_ikinci_kez_eklenemez(client, admin_headers):
    client.post("/drones", json=YENI_DRONE, headers=admin_headers)

    response = client.post("/drones", json=YENI_DRONE, headers=admin_headers)

    assert response.status_code == 409


def test_drone_listelenir(client, admin_headers, drone_factory):
    drone_factory()
    drone_factory()

    response = client.get("/drones", headers=admin_headers)

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_drone_listesi_sayfalanir(client, admin_headers, drone_factory):
    for _ in range(3):
        drone_factory()

    response = client.get("/drones?skip=1&limit=1", headers=admin_headers)

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_tek_drone_getirilir(client, admin_headers, drone):
    response = client.get(f"/drones/{drone.id}", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["id"] == drone.id


def test_olmayan_drone_404_doner(client, admin_headers):
    response = client.get("/drones/9999", headers=admin_headers)

    assert response.status_code == 404


def test_drone_guncellenir(client, admin_headers, drone):
    response = client.patch(
        f"/drones/{drone.id}",
        json={"fuel_percentage": 42.5, "status": "bakimda"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    govde = response.json()
    assert govde["fuel_percentage"] == 42.5
    assert govde["status"] == "bakimda"


def test_kismi_guncelleme_diger_alanlari_bozmaz(client, admin_headers, drone):
    onceki_model = drone.model

    response = client.patch(
        f"/drones/{drone.id}", json={"fuel_percentage": 10.0}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["model"] == onceki_model


def test_drone_silinir(client, admin_headers, drone):
    response = client.delete(f"/drones/{drone.id}", headers=admin_headers)

    assert response.status_code == 204
    assert client.get(f"/drones/{drone.id}", headers=admin_headers).status_code == 404


def test_olmayan_drone_silinemez(client, admin_headers):
    response = client.delete("/drones/9999", headers=admin_headers)

    assert response.status_code == 404


def test_yakit_yuzdesi_100_uzerinde_olamaz(client, admin_headers):
    response = client.post(
        "/drones",
        json={**YENI_DRONE, "fuel_percentage": 120.0},
        headers=admin_headers,
    )

    assert response.status_code == 422


def test_negatif_yakit_reddedilir(client, admin_headers):
    response = client.post(
        "/drones", json={**YENI_DRONE, "fuel_percentage": -1.0}, headers=admin_headers
    )

    assert response.status_code == 422


def test_gecersiz_durum_reddedilir(client, admin_headers):
    response = client.post(
        "/drones", json={**YENI_DRONE, "status": "havada"}, headers=admin_headers
    )

    assert response.status_code == 422


def test_drone_silinince_gorev_ve_telemetrisi_de_silinir(
    client, admin_headers, db_session, drone
):
    """İlişkili kayıtlar cascade ile birlikte silinmeli."""
    from app.models.mission import Mission
    from app.models.telemetry import TelemetryLog
    from app.schemas.mission import MissionCreate
    from app.services import mission as mission_service
    from tests.conftest import telemetri_yaz, zaman

    mission_service.create_mission(
        db_session,
        MissionCreate(drone_id=drone.id, start_location="A", end_location="B"),
    )
    telemetri_yaz(
        db_session,
        [
            {
                "drone_id": drone.id,
                "latitude": 41.0,
                "longitude": 29.0,
                "altitude": 1000.0,
                "fuel_percentage": 90.0,
                "speed": 100.0,
                "timestamp": zaman().isoformat(),
            }
        ],
    )

    client.delete(f"/drones/{drone.id}", headers=admin_headers)

    assert db_session.query(Mission).count() == 0
    assert db_session.query(TelemetryLog).count() == 0


def test_varsayilan_durum_aktiftir(client, admin_headers):
    response = client.post(
        "/drones",
        json={"serial_number": "IHA-777", "model": "Anka"},
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["status"] == DroneStatus.AKTIF.value
    assert response.json()["fuel_percentage"] == 100.0
