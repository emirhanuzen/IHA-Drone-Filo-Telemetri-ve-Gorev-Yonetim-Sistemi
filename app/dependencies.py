"""Ortak FastAPI bağımlılıkları: veritabanı oturumu ve kimlik doğrulama.

`get_current_user`, kullanıcıyı TOKEN PAYLOAD'INDAN üretir; her istekte
veritabanına ekstra bir sorgu atılmaz. Rol de token içinde taşındığı için
yetki kontrolü de sorgusuz yapılır.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError

from app.db.database import get_db
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


__all__ = ["get_db", "get_current_user", "oauth2_scheme"]
