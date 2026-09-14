from sqlalchemy import select

from app.models.user import User

REGISTER_PAYLOAD = {"email": "  Alice@Example.com  ", "password": "correct-horse-battery"}


def test_register_creates_user_with_hashed_password(client, db_session):
    response = client.post("/auth/register", json=REGISTER_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert "password_hash" not in body
    assert "password" not in body

    user = db_session.execute(
        select(User).where(User.email == "alice@example.com")
    ).scalar_one()
    assert user.password_hash != REGISTER_PAYLOAD["password"]


def test_register_rejects_duplicate_email(client):
    client.post("/auth/register", json=REGISTER_PAYLOAD)
    response = client.post("/auth/register", json={"email": "alice@example.com", "password": "another-password"})

    assert response.status_code == 409
