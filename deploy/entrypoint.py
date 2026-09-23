"""Production-only checks. Never print environment values or credentials."""

import os
from pathlib import Path
import re
import sys

from sqlalchemy.engine import URL


def fail(message: str) -> None:
    print(f"Production configuration error: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) < 2:
        fail("a service command is required")

    password = os.environ.get("POSTGRES_PASSWORD", "")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", password):
        fail("POSTGRES_PASSWORD must be 64 hexadecimal characters; use openssl rand -hex 32")

    os.environ["DATABASE_URL"] = URL.create(
        "postgresql+psycopg",
        username=os.environ.get("POSTGRES_USER", "rag"),
        password=password,
        host="db",
        port=5432,
        database=os.environ.get("POSTGRES_DB", "rag"),
    ).render_as_string(hide_password=False)

    if sys.argv[1] != "alembic":
        secret = os.environ.get("JWT_SECRET", "")
        if not re.fullmatch(r"[a-fA-F0-9]{64}", secret):
            fail("JWT_SECRET must be 64 hexadecimal characters; use openssl rand -hex 32")
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key or key.lower() in {"change-me", "changeme", "replace-me"}:
            fail("OPENAI_API_KEY is required")
        upload_dir = Path(os.environ.get("UPLOAD_DIR", "/data/uploads"))
        upload_dir.mkdir(parents=True, exist_ok=True)
        if not os.access(upload_dir, os.W_OK):
            fail("UPLOAD_DIR must be writable by UID 10001")

    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
