import io
import uuid

from app.api import documents as documents_module
from app.config import settings
from app.models.document import Document, DocumentStatus

REGISTER_A = {"email": "owner-a@example.com", "password": "correct-horse-battery"}
REGISTER_B = {"email": "owner-b@example.com", "password": "correct-horse-battery"}


def _auth_headers(client, payload) -> dict:
    client.post("/auth/register", json=payload)
    login = client.post("/auth/login", json={"email": payload["email"], "password": payload["password"]})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _stub_delay(monkeypatch, raise_error: bool = False):
    calls = []

    def fake_delay(document_id):
        if raise_error:
            raise RuntimeError("broker unavailable")
        calls.append(document_id)

    monkeypatch.setattr(documents_module.process_document, "delay", fake_delay)
    return calls


def test_upload_rejects_unsupported_extension(client, monkeypatch):
    _stub_delay(monkeypatch)
    headers = _auth_headers(client, REGISTER_A)

    response = client.post(
        "/documents",
        headers=headers,
        files={"file": ("virus.exe", io.BytesIO(b"binary"), "application/octet-stream")},
    )

    assert response.status_code == 415


def test_upload_rejects_oversized_file(client, monkeypatch):
    _stub_delay(monkeypatch)
    monkeypatch.setattr(settings, "max_upload_mb", 0)  # anything nonzero content exceeds 0 bytes
    headers = _auth_headers(client, REGISTER_A)

    response = client.post(
        "/documents",
        headers=headers,
        files={"file": ("doc.txt", io.BytesIO(b"more than zero bytes"), "text/plain")},
    )

    assert response.status_code == 413


def test_upload_enqueues_task_and_returns_202(client, monkeypatch, db_session):
    calls = _stub_delay(monkeypatch)
    headers = _auth_headers(client, REGISTER_A)

    response = client.post(
        "/documents",
        headers=headers,
        files={"file": ("doc.txt", io.BytesIO(b"hello world"), "text/plain")},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert len(calls) == 1

    document = db_session.get(Document, uuid.UUID(body["id"]))
    assert document is not None
    with open(document.storage_path, "rb") as f:
        assert f.read() == b"hello world"


def test_upload_queue_failure_marks_document_failed_and_returns_503(client, monkeypatch, db_session):
    _stub_delay(monkeypatch, raise_error=True)
    headers = _auth_headers(client, REGISTER_A)

    response = client.post(
        "/documents",
        headers=headers,
        files={"file": ("doc.txt", io.BytesIO(b"hello world"), "text/plain")},
    )

    assert response.status_code == 503

    document = db_session.query(Document).filter_by(filename="doc.txt").one()
    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "Could not queue document for processing"


def test_list_documents_only_returns_own_documents(client, monkeypatch):
    _stub_delay(monkeypatch)
    headers_a = _auth_headers(client, REGISTER_A)
    headers_b = _auth_headers(client, REGISTER_B)

    client.post("/documents", headers=headers_a, files={"file": ("a.txt", io.BytesIO(b"a"), "text/plain")})
    client.post("/documents", headers=headers_b, files={"file": ("b.txt", io.BytesIO(b"b"), "text/plain")})

    response = client.get("/documents", headers=headers_a)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["filename"] == "a.txt"


def test_get_document_404_for_other_user(client, monkeypatch):
    _stub_delay(monkeypatch)
    headers_a = _auth_headers(client, REGISTER_A)
    headers_b = _auth_headers(client, REGISTER_B)

    upload = client.post(
        "/documents", headers=headers_a, files={"file": ("a.txt", io.BytesIO(b"a"), "text/plain")}
    )
    document_id = upload.json()["id"]

    response = client.get(f"/documents/{document_id}", headers=headers_b)

    assert response.status_code == 404


def test_delete_document_removes_row_and_file(client, monkeypatch, db_session):
    _stub_delay(monkeypatch)
    headers = _auth_headers(client, REGISTER_A)

    upload = client.post(
        "/documents", headers=headers, files={"file": ("a.txt", io.BytesIO(b"a"), "text/plain")}
    )
    document_id = upload.json()["id"]
    storage_path = db_session.get(Document, uuid.UUID(document_id)).storage_path

    response = client.delete(f"/documents/{document_id}", headers=headers)

    assert response.status_code == 204
    assert db_session.get(Document, uuid.UUID(document_id)) is None
    import os

    assert not os.path.exists(storage_path)


def test_delete_document_404_for_missing(client, monkeypatch):
    _stub_delay(monkeypatch)
    headers = _auth_headers(client, REGISTER_A)

    response = client.delete(f"/documents/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404
