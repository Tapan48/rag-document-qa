from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import hash_password, verify_password
from app.models.user import User


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def register_user(db: Session, email: str, password: str, *, commit: bool = True) -> User:
    normalized_email = _normalize_email(email)

    existing = db.execute(
        select(User).where(User.email == normalized_email)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(email=normalized_email, password_hash=hash_password(password))
    db.add(user)
    try:
        db.flush()
        if commit:
            db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    normalized_email = _normalize_email(email)
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Incorrect email or password"
    )

    user = db.execute(
        select(User).where(User.email == normalized_email)
    ).scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise unauthorized
    return user
