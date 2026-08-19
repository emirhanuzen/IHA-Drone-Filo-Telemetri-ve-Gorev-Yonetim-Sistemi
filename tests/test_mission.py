"""Görev CRUD ve iş kuralı testleri.

Sınanan kurallar:
  * Bir drone aynı anda yalnızca BİR aktif göreve atanabilir.
  * Yakıtı %20'nin altındaki drone'a yeni görev atanamaz.
  * Görev tamamlandığında/iptal edildiğinde drone yeniden 'aktif' olur.
"""

import pytest

from app.models.enums import DroneStatus, MissionStatus
from app.services import mission as mission_service


def gorev_olustur(client, headers, drone_id, **alanlar):
    govde = {
        "drone_id": drone_id,
        "start_location": "41.01,28.97",
        "end_location": "39.92,32.85",
    }
    govde.update(alanlar)
    return client.post("/missions", json=govde, headers=headers)


def test_gorev_olusturulur(client, commander_headers, drone):
    response = gorev_olustur(client, commander_headers, drone.id)

    assert response.status_code == 201
    govde = response.json()
    assert govde["drone_id"] == drone.id
    assert govde["status"] == MissionStatus.PLANLANDI.value


def test_gorev_atanan_drone_gorevde_olur(client, commander_headers, db_session, drone):
    gorev_olustur(client, commander_headers, drone.id)

    db_session.refresh(drone)
    assert drone.status is DroneStatus.GOREVDE


def test_olmayan_drone_a_gorev_atanamaz(client, commander_headers):
    response = gorev_olustur(client, commander_headers, 9999)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# İş kuralı: çifte atama engeli
# ---------------------------------------------------------------------------


def test_ayni_drone_a_ikinci_aktif_gorev_atanamaz(client, commander_headers, drone):
    gorev_olustur(client, commander_headers, drone.id)

    response = gorev_olustur(client, commander_headers, drone.id)

    assert response.status_code == 409
    assert "cifte atama" in response.json()["detail"].lower()


def test_devam_eden_gorev_varken_yeni_gorev_atanamaz(client, commander_headers, drone):
    mission_id = gorev_olustur(client, commander_headers, drone.id).json()["id"]
    client.patch(
        f"/missions/{mission_id}",
        json={"status": MissionStatus.DEVAM_EDIYOR.value},
        headers=commander_headers,
    )

    response = gorev_olustur(client, commander_headers, drone.id)

    assert response.status_code == 409


def test_gorev_tamamlaninca_yeni_gorev_atanabilir(client, commander_headers, drone):
    mission_id = gorev_olustur(client, commander_headers, drone.id).json()["id"]
    client.patch(
        f"/missions/{mission_id}",
        json={"status": MissionStatus.TAMAMLANDI.value},
        headers=commander_headers,
    )

    response = gorev_olustur(client, commander_headers, drone.id)

    assert response.status_code == 201


def test_gorev_iptal_edilince_yeni_gorev_atanabilir(client, commander_headers, drone):
    mission_id = gorev_olustur(client, commander_headers, drone.id).json()["id"]
    client.patch(
        f"/missions/{mission_id}",
        json={"status": MissionStatus.IPTAL.value},
        headers=commander_headers,
    )

    response = gorev_olustur(client, commander_headers, drone.id)

    assert response.status_code == 201


def test_farkli_drone_lara_ayni_anda_gorev_atanabilir(
    client, commander_headers, drone_factory
):
    birinci = drone_factory()
    ikinci = drone_factory()

    gorev_olustur(client, commander_headers, birinci.id)
    response = gorev_olustur(client, commander_headers, ikinci.id)

    assert response.status_code == 201


# ---------------------------------------------------------------------------
# İş kuralı: yakıt eşiği
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("yakit", [0.0, 5.0, 19.9])
def test_yakiti_dusuk_drone_a_gorev_atanamaz(
    client, commander_headers, drone_factory, yakit
):
    az_yakitli = drone_factory(fuel_percentage=yakit)

    response = gorev_olustur(client, commander_headers, az_yakitli.id)

    assert response.status_code == 409
    assert "yakit" in response.json()["detail"].lower()


@pytest.mark.parametrize("yakit", [20.0, 20.1, 100.0])
def test_yakit_esigindeki_drone_a_gorev_atanabilir(
    client, commander_headers, drone_factory, yakit
):
    uygun = drone_factory(fuel_percentage=yakit)

    response = gorev_olustur(client, commander_headers, uygun.id)

    assert response.status_code == 201


def test_yakit_kurali_servis_katmaninda_da_gecerli(db_session, drone_factory):
    """Kural router katmanında değil, servis katmanında durmalı."""
    from fastapi import HTTPException

    from app.schemas.mission import MissionCreate

    az_yakitli = drone_factory(fuel_percentage=10.0)

    with pytest.raises(HTTPException) as hata:
        mission_service.create_mission(
            db_session,
            MissionCreate(drone_id=az_yakitli.id, start_location="A", end_location="B"),
        )

    assert hata.value.status_code == 409


# ---------------------------------------------------------------------------
# İş kuralı: durum geçişlerinin drone durumuna yansıması
# ---------------------------------------------------------------------------


def test_gorev_tamamlaninca_drone_aktif_olur(
    client, commander_headers, db_session, drone
):
    mission_id = gorev_olustur(client, commander_headers, drone.id).json()["id"]

    response = client.patch(
        f"/missions/{mission_id}",
        json={"status": MissionStatus.TAMAMLANDI.value},
        headers=commander_headers,
    )

    assert response.status_code == 200
    db_session.refresh(drone)
    assert drone.status is DroneStatus.AKTIF


def test_gorev_iptal_edilince_drone_aktif_olur(
    client, commander_headers, db_session, drone
):
    mission_id = gorev_olustur(client, commander_headers, drone.id).json()["id"]

    client.patch(
        f"/missions/{mission_id}",
        json={"status": MissionStatus.IPTAL.value},
        headers=commander_headers,
    )

    db_session.refresh(drone)
    assert drone.status is DroneStatus.AKTIF


def test_gorev_devam_ediyor_olunca_drone_gorevde_kalir(
    client, commander_headers, db_session, drone
):
    mission_id = gorev_olustur(client, commander_headers, drone.id).json()["id"]

    client.patch(
        f"/missions/{mission_id}",
        json={"status": MissionStatus.DEVAM_EDIYOR.value},
        headers=commander_headers,
    )

    db_session.refresh(drone)
    assert drone.status is DroneStatus.GOREVDE


# ---------------------------------------------------------------------------
# Listeleme / okuma / silme
# ---------------------------------------------------------------------------


def test_gorevler_listelenir(client, commander_headers, drone_factory):
    gorev_olustur(client, commander_headers, drone_factory().id)
    gorev_olustur(client, commander_headers, drone_factory().id)

    response = client.get("/missions", headers=commander_headers)

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_gorevler_drone_a_gore_filtrelenir(client, commander_headers, drone_factory):
    birinci = drone_factory()
    ikinci = drone_factory()
    gorev_olustur(client, commander_headers, birinci.id)
    gorev_olustur(client, commander_headers, ikinci.id)

    response = client.get(f"/missions?drone_id={ikinci.id}", headers=commander_headers)

    assert response.status_code == 200
    govde = response.json()
    assert len(govde) == 1
    assert govde[0]["drone_id"] == ikinci.id


def test_tek_gorev_getirilir(client, commander_headers, drone):
    mission_id = gorev_olustur(client, commander_headers, drone.id).json()["id"]

    response = client.get(f"/missions/{mission_id}", headers=commander_headers)

    assert response.status_code == 200
    assert response.json()["id"] == mission_id


def test_olmayan_gorev_404_doner(client, commander_headers):
    response = client.get("/missions/9999", headers=commander_headers)

    assert response.status_code == 404


def test_gorev_silinir(client, commander_headers, drone):
    mission_id = gorev_olustur(client, commander_headers, drone.id).json()["id"]

    response = client.delete(f"/missions/{mission_id}", headers=commander_headers)

    assert response.status_code == 204
    assert (
        client.get(f"/missions/{mission_id}", headers=commander_headers).status_code
        == 404
    )


def test_gecersiz_gorev_durumu_reddedilir(client, commander_headers, drone):
    mission_id = gorev_olustur(client, commander_headers, drone.id).json()["id"]

    response = client.patch(
        f"/missions/{mission_id}", json={"status": "ucuyor"}, headers=commander_headers
    )

    assert response.status_code == 422
