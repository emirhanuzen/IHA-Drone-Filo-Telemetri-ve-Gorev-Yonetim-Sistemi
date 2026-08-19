"""Rol bazlı yetkilendirme testleri (401 / 403 senaryoları).

Rol matrisi:
  * admin     -> her şeye erişir
  * commander -> görev atar / günceller / iptal eder
  * operator  -> telemetri gönderir, elle uyarı açar
  * analyst   -> yalnızca görüntüler

Tablo hâlindeki senaryo listesi, her korumalı uç için hem "tokensiz 401" hem
de "yetkisiz rol 403" durumunu sınar. Yetkili roller içinse yalnızca 403
DÖNMEDİĞİ doğrulanır — kaynağın var olup olmaması (404/409) burada konu değil.
"""

import pytest

from app.models.enums import UserRole

TUM_ROLLER = (
    UserRole.ADMIN,
    UserRole.COMMANDER,
    UserRole.OPERATOR,
    UserRole.ANALYST,
)

DRONE_GOVDE = {
    "serial_number": "IHA-YETKI",
    "model": "Test",
    "fuel_percentage": 90.0,
}
GOREV_GOVDE = {
    "drone_id": 1,
    "start_location": "41.0,29.0",
    "end_location": "39.9,32.8",
}
TELEMETRI_GOVDE = {
    "drone_id": 1,
    "latitude": 41.0,
    "longitude": 29.0,
    "altitude": 1000.0,
    "fuel_percentage": 70.0,
    "speed": 100.0,
}
UYARI_GOVDE = {
    "drone_id": 1,
    "alert_type": "sinyal_kaybi",
    "message": "Sinyal kesildi",
}
KULLANICI_GOVDE = {"username": "yeni_kullanici", "password": "parola123", "role": "analyst"}

# (yöntem, yol, gövde, izinli roller)
SENARYOLAR = [
    # Filo yönetimi: yalnızca admin
    ("POST", "/drones", DRONE_GOVDE, {UserRole.ADMIN}),
    ("PATCH", "/drones/1", {"fuel_percentage": 50.0}, {UserRole.ADMIN}),
    ("DELETE", "/drones/1", None, {UserRole.ADMIN}),
    # Görev yönetimi: commander + admin
    ("POST", "/missions", GOREV_GOVDE, {UserRole.ADMIN, UserRole.COMMANDER}),
    (
        "PATCH",
        "/missions/1",
        {"status": "iptal"},
        {UserRole.ADMIN, UserRole.COMMANDER},
    ),
    ("DELETE", "/missions/1", None, {UserRole.ADMIN, UserRole.COMMANDER}),
    # Telemetri gönderimi: operator + admin
    ("POST", "/telemetry", TELEMETRI_GOVDE, {UserRole.ADMIN, UserRole.OPERATOR}),
    (
        "POST",
        "/telemetry/bulk",
        [TELEMETRI_GOVDE],
        {UserRole.ADMIN, UserRole.OPERATOR},
    ),
    # Elle uyarı açma: operator + admin
    ("POST", "/alerts", UYARI_GOVDE, {UserRole.ADMIN, UserRole.OPERATOR}),
    # Kullanıcı yönetimi: yalnızca admin
    ("POST", "/users", KULLANICI_GOVDE, {UserRole.ADMIN}),
    ("GET", "/users", None, {UserRole.ADMIN}),
    # Görüntüleme: kimliği doğrulanmış her rol
    ("GET", "/drones", None, set(TUM_ROLLER)),
    ("GET", "/missions", None, set(TUM_ROLLER)),
    ("GET", "/telemetry", None, set(TUM_ROLLER)),
    ("GET", "/alerts", None, set(TUM_ROLLER)),
    ("GET", "/auth/me", None, set(TUM_ROLLER)),
]


def istek_at(client, yontem, yol, govde=None, headers=None):
    """Senaryo tablosundaki isteği ilgili HTTP yöntemiyle gönderir."""
    kwargs = {"headers": headers or {}}
    if govde is not None:
        kwargs["json"] = govde
    return client.request(yontem, yol, **kwargs)


@pytest.mark.parametrize(
    "yontem,yol,govde,izinli",
    SENARYOLAR,
    ids=[f"{s[0]} {s[1]}" for s in SENARYOLAR],
)
def test_tokensiz_istek_401_doner(client, yontem, yol, govde, izinli):
    response = istek_at(client, yontem, yol, govde)

    assert response.status_code == 401


@pytest.mark.parametrize(
    "yontem,yol,govde,izinli",
    SENARYOLAR,
    ids=[f"{s[0]} {s[1]}" for s in SENARYOLAR],
)
def test_yetkisiz_rol_403_doner(client, auth_headers, yontem, yol, govde, izinli):
    yasakli_roller = [rol for rol in TUM_ROLLER if rol not in izinli]

    for rol in yasakli_roller:
        response = istek_at(client, yontem, yol, govde, auth_headers(rol))
        assert response.status_code == 403, f"{rol.value} icin 403 bekleniyordu"


@pytest.mark.parametrize(
    "yontem,yol,govde,izinli",
    SENARYOLAR,
    ids=[f"{s[0]} {s[1]}" for s in SENARYOLAR],
)
def test_izinli_rol_403_almaz(client, auth_headers, yontem, yol, govde, izinli):
    for rol in sorted(izinli, key=lambda r: r.value):
        response = istek_at(client, yontem, yol, govde, auth_headers(rol))
        assert response.status_code != 403, f"{rol.value} erisebilmeliydi"
        assert response.status_code != 401


def test_admin_operator_uclarina_da_erisir(client, admin_headers, drone):
    """Admin, tanımı gereği diğer rollerin uçlarını da kullanabilir."""
    response = client.post(
        "/telemetry",
        json={**TELEMETRI_GOVDE, "drone_id": drone.id},
        headers=admin_headers,
    )

    assert response.status_code == 201


def test_admin_commander_uclarina_da_erisir(client, admin_headers, drone):
    response = client.post(
        "/missions", json={**GOREV_GOVDE, "drone_id": drone.id}, headers=admin_headers
    )

    assert response.status_code == 201


def test_403_mesaji_gerekli_rolleri_soyler(client, analyst_headers):
    response = client.post("/drones", json=DRONE_GOVDE, headers=analyst_headers)

    assert response.status_code == 403
    assert "admin" in response.json()["detail"]


def test_kayit_ve_giris_token_istemez(client):
    kayit = client.post(
        "/auth/register",
        json={"username": "acik_uc", "password": "parola123", "role": "analyst"},
    )
    giris = client.post(
        "/auth/login", data={"username": "acik_uc", "password": "parola123"}
    )

    assert kayit.status_code == 201
    assert giris.status_code == 200


def test_admin_kullanici_olusturabilir(client, admin_headers):
    response = client.post("/users", json=KULLANICI_GOVDE, headers=admin_headers)

    assert response.status_code == 201
    assert response.json()["role"] == "analyst"


def test_admin_ayricalikli_rolde_kullanici_olusturabilir(client, admin_headers):
    """Herkese açık kayıt commander veremez; admin verebilir."""
    response = client.post(
        "/users",
        json={"username": "komutan", "password": "parola123", "role": "commander"},
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["role"] == "commander"


def test_admin_kullanicilari_listeler(client, admin_headers):
    client.post("/users", json=KULLANICI_GOVDE, headers=admin_headers)

    response = client.get("/users", headers=admin_headers)

    assert response.status_code == 200
    assert len(response.json()) == 1
