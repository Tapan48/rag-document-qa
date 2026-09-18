from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.database import engine, get_db
from app.main import app


@pytest.fixture(autouse=True)
def _clean_uploads():
    upload_dir = Path(settings.upload_dir)
    before = set(upload_dir.iterdir()) if upload_dir.exists() else set()

    yield

    if upload_dir.exists():
        for path in upload_dir.iterdir():
            if path not in before:
                path.unlink(missing_ok=True)


@pytest.fixture()
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    session: Session = session_factory()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
