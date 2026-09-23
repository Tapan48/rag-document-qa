"""Server-only account creation: python -m app.cli create-user --email EMAIL."""

import argparse
import getpass
import sys
import warnings

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.auth.schemas import UserCreate
from app.auth.service import register_user
from app.database import SessionLocal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage reviewer accounts on the server")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user", help="Create an account with a hidden password prompt")
    create.add_argument("--email", required=True)
    args = parser.parse_args(argv)

    try:
        # Refuse getpass's echoing fallback when no terminal is available.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("Password (at least 8 characters): ")
            confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            print("Passwords do not match. No account created.", file=sys.stderr)
            return 2
        payload = UserCreate(email=args.email, password=password)
        with SessionLocal() as db:
            user = register_user(db, payload.email, payload.password)
            print(f"Account created: {user.email}")
        return 0
    except ValidationError as exc:
        # Never render ValidationError itself: it includes submitted inputs.
        for error in exc.errors(include_input=False, include_url=False):
            print(f"Invalid {error['loc'][0]}: {error['msg']}", file=sys.stderr)
        return 2
    except HTTPException as exc:
        message = "Email already registered." if exc.status_code == 409 else "Account creation failed."
        print(message, file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("Database operation failed. Check server configuration.", file=sys.stderr)
        return 1
    except (getpass.GetPassWarning, EOFError):
        print("A terminal with hidden password input is required. Do not use -T.", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nCancelled. No account created.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
