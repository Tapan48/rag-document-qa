REGISTER_PAYLOAD = {"email": "  Alice@Example.com  ", "password": "correct-horse-battery"}


def test_login_succeeds_with_correct_credentials(client):
    client.post("/auth/register", json=REGISTER_PAYLOAD)

    response = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": "correct-horse-battery"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_rejects_wrong_password(client):
    client.post("/auth/register", json=REGISTER_PAYLOAD)

    response = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": "wrong-password"}
    )

    assert response.status_code == 401


def test_login_rejects_unknown_email_with_same_status_as_wrong_password(client):
    response = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever123"}
    )

    assert response.status_code == 401
