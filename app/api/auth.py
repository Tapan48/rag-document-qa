from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import Token, UserCreate, UserLogin, UserPublic
from app.auth.security import create_access_token
from app.auth.service import authenticate_user, register_user
from app.database import get_db
from app.models.user import User
from app.config import settings
from app.access.service import register_invited_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config")
def auth_config() -> dict[str, bool | str]:
    mode = settings.effective_registration_mode
    return {"registration_enabled": mode == "open", "registration_mode": mode}


@router.post("/register", response_model=UserPublic, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    mode = settings.effective_registration_mode
    if mode == "closed":
        raise HTTPException(status_code=403, detail="Registration is invite-only")
    if mode == "approval":
        if not payload.invitation_token:
            raise HTTPException(status_code=403, detail="Request access and use the registration link emailed after approval")
        return register_invited_user(db, payload.email, payload.password, payload.invitation_token)
    return register_user(db, payload.email, payload.password)


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> Token:
    user = authenticate_user(db, payload.email, payload.password)
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
