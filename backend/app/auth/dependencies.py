from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession

from app.auth.security import hash_csrf_token, hash_session_token, secure_compare
from app.core.config import get_settings
from app.db.models.identity import Session, User
from app.db.session import get_db


@dataclass(frozen=True, slots=True)
class AuthContext:
    user: User
    session: Session


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def require_user(
    request: Request,
    db: DatabaseSession = Depends(get_db),
) -> AuthContext:
    session_token = request.cookies.get(get_settings().session_cookie_name)
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required."
        )
    token_hash = hash_session_token(session_token)
    result = db.execute(
        select(Session, User)
        .join(User, User.id == Session.user_id)
        .where(
            Session.token_hash == token_hash, Session.revoked_at.is_(None), User.status == "active"
        )
    ).one_or_none()
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required."
        )
    session, user = result
    if not secure_compare(token_hash, session.token_hash) or _as_utc(
        session.expires_at
    ) <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required."
        )
    return AuthContext(user=user, session=session)


def require_csrf(
    request: Request,
    auth: AuthContext = Depends(require_user),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> AuthContext:
    csrf_cookie = request.cookies.get(get_settings().csrf_cookie_name)
    origin = request.headers.get("Origin")
    if origin not in get_settings().cors_origin_strings:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Request origin is not allowed."
        )
    if not csrf_header or not csrf_cookie or not secure_compare(csrf_header, csrf_cookie):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")
    if not secure_compare(hash_csrf_token(csrf_header), auth.session.csrf_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")
    return auth
