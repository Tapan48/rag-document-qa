import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings

REGISTER_PAYLOAD = {"email": "  Alice@Example.com  ", "password": "correct-horse-battery"}


def test_me_rejects_missing_token(client):
    response = client.get("/auth/me")

    assert response.status_code in (401, 403)


def test_me_rejects_tampered_token(client):
    response = client.get(
        "/auth/me", headers={"Authorization": "Bearer not.a.validtoken"}
    )

    assert response.status_code == 401


def test_me_rejects_expired_token(client):
    expired_token = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})

    assert response.status_code == 401


def test_me_returns_current_user_for_valid_token(client):
    client.post("/auth/register", json=REGISTER_PAYLOAD)
    login_response = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": "correct-horse-battery"}
    )
    token = login_response.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "alice@example.com"
