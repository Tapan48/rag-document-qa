from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.schemas import UserCreate, UserPublic
from app.auth.service import register_user
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    return register_user(db, payload.email, payload.password)
