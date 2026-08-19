"""Kimlik doğrulama testleri: kayıt, giriş, token çözümleme."""

from datetime import timedelta

from app.models.enums import UserRole
from app.models.user import User
from app.security import create_access_token


def kayit_ol(client, username="pilot", password="parola123", role="operator"):
    return client.post(
        "/auth/register",
        json={"username": username, "password": password, "role": role},
    )


def giris_yap(client, username="pilot", password="parola123"):
    return client.post(
        "/auth/login", data={"username": username, "password": password}
    )


def test_health_kimlik_dogrulama_istemez(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_kayit_yeni_kullanici_olusturur(client):
    response = kayit_ol(client)

    assert response.status_code == 201
    govde = response.json()
    assert govde["username"] == "pilot"
    assert govde["role"] == "operator"
    assert govde["is_active"] is True
    # Parola hiçbir biçimde yanıtta dönmemeli.
    assert "password" not in govde
    assert "hashed_password" not in govde


def test_kayitta_parola_ozetlenerek_saklanir(client, db_session):
    kayit_ol(client)

    user = db_session.query(User).filter(User.username == "pilot").one()
    assert user.hashed_password != "parola123"
    assert user.hashed_password.startswith("$2")


def test_ayni_kullanici_adi_ikinci_kez_alinamaz(client):
    kayit_ol(client)

    response = kayit_ol(client)

    assert response.status_code == 409


def test_ilk_kullanici_admin_olabilir(client):
    response = kayit_ol(client, username="kurucu", role="admin")

    assert response.status_code == 201
    assert response.json()["role"] == "admin"


def test_sonraki_kullanici_kendine_admin_rolu_veremez(client):
    kayit_ol(client, username="ilk")

    response = kayit_ol(client, username="sinsi", role="admin")

    assert response.status_code == 403


def test_sonraki_kullanici_kendine_commander_rolu_veremez(client):
    kayit_ol(client, username="ilk")

    response = kayit_ol(client, username="sinsi2", role="commander")

    assert response.status_code == 403


def test_kisa_parola_reddedilir(client):
    response = kayit_ol(client, username="kisa", password="123")

    assert response.status_code == 422


def test_giris_token_dondurur(client):
    kayit_ol(client)

    response = giris_yap(client)

    assert response.status_code == 200
    govde = response.json()
    assert govde["token_type"] == "bearer"
    assert govde["access_token"]


def test_hatali_parola_ile_giris_401_doner(client):
    kayit_ol(client)

    response = giris_yap(client, password="yanlisparola")

    assert response.status_code == 401


def test_olmayan_kullanici_ile_giris_401_doner(client):
    response = giris_yap(client, username="hayalet")

    assert response.status_code == 401


def test_pasif_kullanici_giris_yapamaz(client, db_session):
    kayit_ol(client)
    user = db_session.query(User).filter(User.username == "pilot").one()
    user.is_active = False
    db_session.commit()

    response = giris_yap(client)

    assert response.status_code == 403


def test_me_token_sahibini_doner(client):
    kayit_ol(client)
    token = giris_yap(client).json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    govde = response.json()
    assert govde["username"] == "pilot"
    assert govde["role"] == "operator"


def test_me_tokensiz_401_doner(client):
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_bozuk_token_401_doner(client):
    response = client.get(
        "/auth/me", headers={"Authorization": "Bearer bu.bir.token.degil"}
    )

    assert response.status_code == 401


def test_suresi_dolmus_token_401_doner(client):
    token = create_access_token(
        user_id=1,
        username="pilot",
        role=UserRole.OPERATOR,
        expires_delta=timedelta(minutes=-5),
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_yanlis_anahtarla_imzalanmis_token_401_doner(client):
    from jose import jwt

    token = jwt.encode(
        {"sub": "sahtekar", "uid": 1, "role": "admin"},
        "baska-bir-anahtar",
        algorithm="HS256",
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_taninmayan_rol_iceren_token_401_doner(client):
    from jose import jwt

    from app.config import settings

    token = jwt.encode(
        {"sub": "pilot", "uid": 1, "role": "general"},
        settings.secret_key,
        algorithm=settings.algorithm,
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
