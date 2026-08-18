from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UserRole


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, examples=["emirhan"])


class UserCreate(UserBase):
    # bcrypt en fazla 72 bayt işler; sınır burada da uygulanır.
    password: str = Field(..., min_length=6, max_length=72)
    role: UserRole = UserRole.OPERATOR


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: UserRole
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    """Giriş sonrası dönen erişim token'ı."""

    access_token: str
    token_type: str = "bearer"


class CurrentUser(BaseModel):
    """Token payload'ından üretilen, o anki isteğin kullanıcısı.

    Veritabanından okunmaz; alanlar doğrudan JWT içinden gelir.
    """

    id: int
    username: str
    role: UserRole
