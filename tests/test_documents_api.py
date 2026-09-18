import io
import os
import uuid

from app.config import settings
from app.models.document import Document

REGISTER_A = {"email": "owner-a@example.com", "password": "correct-horse-battery"}
REGISTER_B = {"email": "owner-b@example.com", "password": "correct-horse-battery"}


def _auth_headers(client, payload) -> dict:
    client.post("/auth/register", json=payload)
    login = client.post("/auth/login", json={"email": payload["email"], "password": payload["password"]})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_upload_rejects_unsupported_extension(client):
    headers = _auth_headers(client, REGISTER_A)

    response = client.post(
        "/documents",
        headers=headers,
        files={"file": ("virus.exe", io.BytesIO(b"binary"), "application/octet-stream")},
    )

    assert response.status_code == 415


def test_upload_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 0)  # anything nonzero content exceeds 0 bytes
    headers = _auth_headers(client, REGISTER_A)

    response = client.post(
        "/documents",
        headers=headers,
        files={"file": ("doc.txt", io.BytesIO(b"more than zero bytes"), "text/plain")},
    )

    assert response.status_code == 413


def test_upload_returns_202_and_creates_document(client, db_session):
    headers = _auth_headers(client, REGISTER_A)

    response = client.post(
        "/documents",
        headers=headers,
        files={"file": ("doc.txt", io.BytesIO(b"hello world"), "text/plain")},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"

    document = db_session.get(Document, uuid.UUID(body["id"]))
    assert document is not None
    with open(document.storage_path, "rb") as f:
        assert f.read() == b"hello world"


def test_list_documents_only_returns_own_documents(client):
    headers_a = _auth_headers(client, REGISTER_A)
    headers_b = _auth_headers(client, REGISTER_B)

    client.post("/documents", headers=headers_a, files={"file": ("a.txt", io.BytesIO(b"a"), "text/plain")})
    client.post("/documents", headers=headers_b, files={"file": ("b.txt", io.BytesIO(b"b"), "text/plain")})

    response = client.get("/documents", headers=headers_a)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["filename"] == "a.txt"


def test_get_document_404_for_other_user(client):
    headers_a = _auth_headers(client, REGISTER_A)
    headers_b = _auth_headers(client, REGISTER_B)

    upload = client.post(
        "/documents", headers=headers_a, files={"file": ("a.txt", io.BytesIO(b"a"), "text/plain")}
    )
    document_id = upload.json()["id"]

    response = client.get(f"/documents/{document_id}", headers=headers_b)

    assert response.status_code == 404


def test_delete_document_removes_row_and_file(client, db_session):
    headers = _auth_headers(client, REGISTER_A)

    upload = client.post(
        "/documents", headers=headers, files={"file": ("a.txt", io.BytesIO(b"a"), "text/plain")}
    )
    document_id = upload.json()["id"]
    storage_path = db_session.get(Document, uuid.UUID(document_id)).storage_path

    response = client.delete(f"/documents/{document_id}", headers=headers)

    assert response.status_code == 204
    assert db_session.get(Document, uuid.UUID(document_id)) is None
    assert not os.path.exists(storage_path)


def test_delete_document_404_for_missing(client):
    headers = _auth_headers(client, REGISTER_A)

    response = client.delete(f"/documents/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404
