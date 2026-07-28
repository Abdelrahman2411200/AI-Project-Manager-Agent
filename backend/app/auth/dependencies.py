from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session as DatabaseSession

from app.auth.security import hash_csrf_token, hash_session_token, secure_compare
from app.core.config import get_settings
from app.db.models.identity import Session, User
from app.db.models.run import ACTIVE_RUN_STATUSES, AgentRun
from app.db.session import get_db


@dataclass(frozen=True, slots=True)
class AuthContext:
    user: User
    session: Session


@dataclass(frozen=True, slots=True)
class AuthUsageContext:
    owner_id: UUID
    runs_used: int
    tokens_reserved_or_used: int
    resets_at: datetime


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _session_token_hash(request: Request) -> str:
    session_token = request.cookies.get(get_settings().session_cookie_name)
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required."
        )
    return hash_session_token(session_token)


def _validate_auth(
    token_hash: str,
    session: Session,
    user: User,
    *,
    now: datetime,
) -> AuthContext:
    _validate_session_values(
        token_hash,
        stored_hash=session.token_hash,
        expires_at=session.expires_at,
        now=now,
    )
    return AuthContext(user=user, session=session)


def _validate_session_values(
    token_hash: str,
    *,
    stored_hash: str,
    expires_at: datetime,
    now: datetime,
) -> None:
    if not secure_compare(token_hash, stored_hash) or _as_utc(expires_at) <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required."
        )


def require_user(
    request: Request,
    db: DatabaseSession = Depends(get_db),
) -> AuthContext:
    token_hash = _session_token_hash(request)
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
    return _validate_auth(token_hash, session, user, now=datetime.now(UTC))


def require_user_usage(
    request: Request,
    db: DatabaseSession = Depends(get_db),
) -> AuthUsageContext:
    token_hash = _session_token_hash(request)
    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    resets_at = day_start + timedelta(days=1)
    reserved_tokens = case(
        (
            AgentRun.status.in_(ACTIVE_RUN_STATUSES),
            AgentRun.token_budget,
        ),
        else_=AgentRun.tokens_used,
    )
    result = db.execute(
        select(
            Session.token_hash,
            Session.expires_at,
            User.id,
            func.count(AgentRun.id).label("runs_used"),
            func.coalesce(func.sum(reserved_tokens), 0).label("tokens_reserved_or_used"),
        )
        .join(User, User.id == Session.user_id)
        .outerjoin(
            AgentRun,
            and_(
                AgentRun.initiator_id == User.id,
                AgentRun.created_at >= day_start,
            ),
        )
        .where(
            Session.token_hash == token_hash,
            Session.revoked_at.is_(None),
            User.status == "active",
        )
        .group_by(Session.token_hash, Session.expires_at, User.id)
    ).one_or_none()
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required."
        )
    stored_hash, expires_at, owner_id, run_count, token_count = result
    _validate_session_values(
        token_hash,
        stored_hash=stored_hash,
        expires_at=expires_at,
        now=now,
    )
    return AuthUsageContext(
        owner_id=owner_id,
        runs_used=int(run_count),
        tokens_reserved_or_used=int(token_count),
        resets_at=resets_at,
    )


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
