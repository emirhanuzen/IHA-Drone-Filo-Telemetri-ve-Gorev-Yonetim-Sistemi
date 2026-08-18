"""Ortak FastAPI bağımlılıkları: veritabanı oturumu, kimlik doğrulama, yetki.

`get_current_user`, kullanıcıyı TOKEN PAYLOAD'INDAN üretir; her istekte
veritabanına ekstra bir sorgu atılmaz. Rol de token içinde taşındığı için
yetki kontrolü de sorgusuz yapılır.
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError

from app.db.database import get_db
from app.models.enums import UserRole
from app.schemas.user import CurrentUser
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Kimlik dogrulanamadi",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    """Bearer token'ı çözer ve isteğin kullanıcısını döner."""
    payload = decode_access_token(token)
    if payload is None:
        raise CREDENTIALS_EXCEPTION

    try:
        return CurrentUser(
            id=payload["uid"],
            username=payload["sub"],
            role=payload["role"],
        )
    except (KeyError, ValidationError):
        # Eksik ya da tanınmayan rol içeren token.
        raise CREDENTIALS_EXCEPTION


def require_roles(*roles: UserRole) -> Callable[..., CurrentUser]:
    """Verilen rollerden birine sahip olmayı şart koşan bağımlılık üretir.

    Rol, token payload'ından okunur — kontrol için veritabanına GİDİLMEZ.
    Admin, tanımı gereği her şeye erişebildiği için ayrıca listelenmesine
    gerek yoktur.
    """
    allowed = set(roles)

    def dependency(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if current_user.role is UserRole.ADMIN or current_user.role in allowed:
            return current_user

        izinli = ", ".join(sorted(role.value for role in allowed | {UserRole.ADMIN}))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Bu islem icin yetkiniz yok. Gerekli rol(ler): {izinli}",
        )

    return dependency


# Sık kullanılan yetki bileşimleri.
require_admin = require_roles(UserRole.ADMIN)
require_mission_manager = require_roles(UserRole.COMMANDER)
require_telemetry_sender = require_roles(UserRole.OPERATOR)

__all__ = [
    "get_db",
    "get_current_user",
    "oauth2_scheme",
    "require_roles",
    "require_admin",
    "require_mission_manager",
    "require_telemetry_sender",
]
