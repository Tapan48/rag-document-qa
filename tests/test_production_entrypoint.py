"""Production configuration must fail closed without disclosing credentials."""

import os
import secrets
import sys

import pytest
from sqlalchemy.engine import make_url

from deploy import entrypoint


@pytest.fixture
def production_env(monkeypatch, tmp_path):
    monkeypatch.setenv("POSTGRES_PASSWORD", secrets.token_hex(32))
    monkeypatch.setenv("JWT_SECRET", secrets.token_hex(32))
    monkeypatch.setenv("OPENAI_API_KEY", "mock-provider-only")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(sys, "argv", ["entrypoint.py", "uvicorn", "app.main:app"])


@pytest.mark.parametrize("field", ["POSTGRES_PASSWORD", "JWT_SECRET", "OPENAI_API_KEY"])
def test_missing_secret_blocks_startup(monkeypatch, production_env, field, capsys):
    monkeypatch.delenv(field)
    with pytest.raises(SystemExit, match="1"):
        entrypoint.main()
    assert field in capsys.readouterr().err


@pytest.mark.parametrize("field", ["POSTGRES_PASSWORD", "JWT_SECRET"])
def test_invalid_secret_is_not_logged(monkeypatch, production_env, field, capsys):
    bad_secret = "invalid-value-that-must-never-appear-in-logs"
    monkeypatch.setenv(field, bad_secret)
    with pytest.raises(SystemExit):
        entrypoint.main()
    output = capsys.readouterr()
    assert bad_secret not in output.err + output.out


def test_database_url_and_upload_directory(monkeypatch, production_env):
    called = []
    monkeypatch.setenv("DATABASE_URL", "postgresql://stale:wrong@external/other")
    monkeypatch.setattr(os, "execvp", lambda *args: called.append(args))
    entrypoint.main()
    url = make_url(os.environ["DATABASE_URL"])
    assert url.host == "db"
    assert url.password == os.environ["POSTGRES_PASSWORD"]
    assert os.access(os.environ["UPLOAD_DIR"], os.W_OK)
    assert called == [("uvicorn", ["uvicorn", "app.main:app"])]


def test_migration_does_not_require_application_secrets(monkeypatch, production_env):
    monkeypatch.delenv("JWT_SECRET")
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setattr(sys, "argv", ["entrypoint.py", "alembic", "upgrade", "head"])
    called = []
    monkeypatch.setattr(os, "execvp", lambda *args: called.append(args))
    entrypoint.main()
    assert called == [("alembic", ["alembic", "upgrade", "head"])]


def test_unwritable_upload_directory_blocks_startup(monkeypatch, production_env, capsys):
    monkeypatch.setattr(os, "access", lambda *args: False)
    with pytest.raises(SystemExit):
        entrypoint.main()
    assert "writable" in capsys.readouterr().err
