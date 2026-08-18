from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.schemas.user import CurrentUser, Token, UserCreate, UserResponse
from app.services import user as user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> UserResponse:
    """Yeni kullanıcı kaydı açar (kimlik doğrulama gerektirmez)."""
    return user_service.create_user(db, payload)


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> Token:
    """Kullanıcı adı ve parola ile erişim token'ı alır."""
    return user_service.authenticate(db, form_data.username, form_data.password)


@router.get("/me", response_model=CurrentUser)
def read_current_user(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Token'ın sahibini döner; veritabanına gidilmez."""
    return current_user
