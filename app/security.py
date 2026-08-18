"""Parola özetleme ve JWT üretimi/çözümlemesi.

Token payload'ına kullanıcının rolü de yazılır; böylece yetki kontrolü için
her istekte veritabanına gitmek gerekmez.
"""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.models.enums import UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Parolayı bcrypt ile özetler."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Girilen parolayı, kayıtlı özet ile karşılaştırır."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    user_id: int,
    username: str,
    role: UserRole,
    expires_delta: timedelta | None = None,
) -> str:
    """Kullanıcı için imzalı bir JWT üretir."""
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {
        "sub": username,
        "uid": user_id,
        "role": role.value,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict | None:
    """Token'ı doğrular ve payload'ını döner; geçersizse None döner."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
