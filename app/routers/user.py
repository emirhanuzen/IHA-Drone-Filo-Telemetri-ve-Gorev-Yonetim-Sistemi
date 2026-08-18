from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.dependencies import get_db, require_admin
from app.schemas.user import UserCreate, UserResponse
from app.services import user as user_service

# Kullanıcı yönetimi tamamen admin'e aittir. Commander/admin rolleri ancak
# buradan atanabilir; herkese açık /auth/register bu rolleri veremez.
router = APIRouter(
    prefix="/users", tags=["users"], dependencies=[Depends(require_admin)]
)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> UserResponse:
    """Admin olarak, istenen rolde yeni bir kullanıcı oluşturur."""
    return user_service.create_user(db, payload, by_admin=True)


@router.get("", response_model=list[UserResponse])
def list_users(
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
) -> list[UserResponse]:
    return user_service.list_users(db, skip=skip, limit=limit)
