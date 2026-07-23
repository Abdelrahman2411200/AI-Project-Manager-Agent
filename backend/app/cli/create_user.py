import argparse
from getpass import getpass

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from app.auth.security import hash_password, normalize_email
from app.db.models.identity import User
from app.db.session import SessionLocal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an AI Project Manager owner account.")
    parser.add_argument("--email", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        email = normalize_email(str(TypeAdapter(EmailStr).validate_python(args.email)))
    except ValidationError:
        print("A valid email address is required.")
        return 2
    password = getpass("Password (12+ characters): ")
    confirmation = getpass("Confirm password: ")
    if len(password) < 12 or password != confirmation:
        print("Passwords must match and contain at least 12 characters.")
        return 2
    with SessionLocal() as session:
        if session.scalar(select(User.id).where(User.email == email)) is not None:
            print("An account with that email already exists.")
            return 1
        session.add(User(email=email, password_hash=hash_password(password)))
        session.commit()
    print(f"Created owner account: {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
