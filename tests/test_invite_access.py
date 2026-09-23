from contextlib import nullcontext
import getpass
import warnings

import pytest
from sqlalchemy import select

from app import cli
from app.config import settings
from app.models.user import User


@pytest.mark.parametrize("enabled", [True, False])
def test_public_config_exposes_only_registration_flag(client, monkeypatch, enabled):
    monkeypatch.setattr(settings, "registration_enabled", enabled)
    response = client.get("/auth/config")
    assert response.status_code == 200
    assert response.json() == {"registration_enabled": enabled}


def test_disabled_registration_creates_no_user(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "registration_enabled", False)
    response = client.post("/auth/register", json={"email": "visitor@example.com", "password": "test-password"})
    assert response.status_code == 403
    assert db_session.scalar(select(User).where(User.email == "visitor@example.com")) is None


def prompt_passwords(monkeypatch, *values):
    passwords = iter(values)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(passwords))


def test_cli_user_can_login_with_registration_disabled(client, db_session, monkeypatch, capsys):
    monkeypatch.setattr(settings, "registration_enabled", False)
    monkeypatch.setattr(cli, "SessionLocal", lambda: nullcontext(db_session))
    password = "reviewer-test-password"
    prompt_passwords(monkeypatch, password, password)
    assert cli.main(["create-user", "--email", "Reviewer@Example.com"]) == 0
    assert password not in capsys.readouterr().out
    response = client.post("/auth/login", json={"email": "reviewer@example.com", "password": password})
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    user = db_session.scalar(select(User).where(User.email == "reviewer@example.com"))
    original_hash = user.password_hash
    assert original_hash != password
    prompt_passwords(monkeypatch, "another-password", "another-password")
    assert cli.main(["create-user", "--email", "reviewer@example.com"]) == 1
    assert "already registered" in capsys.readouterr().err
    assert user.password_hash == original_hash


@pytest.mark.parametrize("email,first,second", [
    ("reviewer@example.com", "valid-password", "different-password"),
    ("reviewer@example.com", "short", "short"),
    ("invalid-email", "valid-password", "valid-password"),
])
def test_cli_validation_does_not_open_database_or_echo_password(monkeypatch, capsys, email, first, second):
    prompt_passwords(monkeypatch, first, second)
    monkeypatch.setattr(cli, "SessionLocal", lambda: pytest.fail("Database should not be opened"))
    assert cli.main(["create-user", "--email", email]) == 2
    output = capsys.readouterr()
    assert first not in output.out + output.err
    assert second not in output.out + output.err


def test_cli_refuses_password_echo_fallback(monkeypatch, capsys):
    def no_terminal(_):
        warnings.warn("Cannot control echo", getpass.GetPassWarning)
    monkeypatch.setattr(cli.getpass, "getpass", no_terminal)
    assert cli.main(["create-user", "--email", "reviewer@example.com"]) == 2
    assert "hidden password input is required" in capsys.readouterr().err
