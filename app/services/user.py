"""Kullanıcı (User) iş mantığı: kayıt, kimlik doğrulama, token üretimi."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import Token, UserCreate
from app.security import create_access_token, hash_password, verify_password

# Herkese açık kayıt ile alınamayan, yetkili roller. İlk kullanıcı hariç
# (sistemin ilk yöneticisi bir şekilde oluşabilmeli) bu roller yalnızca bir
# admin tarafından atanabilir.
PRIVILEGED_ROLES = (UserRole.ADMIN, UserRole.COMMANDER)


def get_user_by_username(db: Session, username: str) -> User | None:
    """Kullanıcıyı adına göre getirir; yoksa None döner."""
    return db.scalar(select(User).where(User.username == username))


def list_users(db: Session, skip: int = 0, limit: int = 100) -> list[User]:
    """Kullanıcıları sayfalı olarak listeler."""
    stmt = select(User).offset(skip).limit(limit).order_by(User.id)
    return list(db.scalars(stmt).all())


def _is_first_user(db: Session) -> bool:
    """Sistemde hiç kullanıcı var mı?"""
    return db.scalar(select(User.id).limit(1)) is None


def create_user(db: Session, data: UserCreate, by_admin: bool = False) -> User:
    """Yeni kullanıcı oluşturur.

    `by_admin` False ise (herkese açık kayıt), admin/commander rolü yalnızca
    sistemin ilk kullanıcısı için verilebilir; sonrasında bu roller admin
    tarafından atanır.
    """
    if get_user_by_username(db, data.username) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu kullanici adi zaten alinmis",
        )

    role = data.role
    if role in PRIVILEGED_ROLES and not by_admin and not _is_first_user(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"'{role.value}' rolu yalnizca bir admin tarafindan atanabilir"
            ),
        )

    user = User(
        username=data.username,
        hashed_password=hash_password(data.password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, username: str, password: str) -> Token:
    """Kullanıcı adı/parolayı doğrular ve erişim token'ı üretir."""
    user = get_user_by_username(db, username)
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanici adi veya parola hatali",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Kullanici pasif durumda"
        )

    token = create_access_token(user_id=user.id, username=user.username, role=user.role)
    return Token(access_token=token)
