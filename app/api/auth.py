from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.schemas import Token, UserCreate, UserLogin, UserPublic
from app.auth.security import create_access_token
from app.auth.service import authenticate_user, register_user
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    return register_user(db, payload.email, payload.password)


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> Token:
    user = authenticate_user(db, payload.email, payload.password)
    return Token(access_token=create_access_token(user.id))
