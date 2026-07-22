from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession

from app.auth.dependencies import AuthContext, require_csrf, require_user
from app.auth.security import (
    create_session_credentials,
    login_rate_limiter,
    normalize_email,
    verify_password,
)
from app.core.config import get_settings
from app.db.models.identity import Session, User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, SessionView, UserView
from app.services.audit import AuditRecorder

router = APIRouter(prefix="/auth", tags=["authentication"])


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _validate_origin(request: Request) -> None:
    if request.headers.get("Origin") not in get_settings().cors_origin_strings:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Request origin is not allowed."
        )


@router.post("/session", response_model=SessionView)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DatabaseSession = Depends(get_db),
) -> SessionView:
    _validate_origin(request)
    email = normalize_email(str(payload.email))
    address = request.client.host if request.client else "unknown"
    rate_keys = (f"ip:{address}", f"user:{email}")
    retry_windows = [
        retry_after
        for key in rate_keys
        if (retry_after := login_rate_limiter.check(key)) is not None
    ]
    if retry_windows:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(max(retry_windows))},
        )
    user = db.scalar(select(User).where(User.email == email, User.status == "active"))
    if user is None or not verify_password(payload.password, user.password_hash):
        for key in rate_keys:
            login_rate_limiter.record_failure(key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password."
        )
    login_rate_limiter.reset(f"user:{email}")
    now = datetime.now(UTC)
    credentials = create_session_credentials(now)
    session = Session(
        user_id=user.id,
        token_hash=credentials.session_hash,
        csrf_hash=credentials.csrf_hash,
        created_at=now,
        expires_at=credentials.expires_at,
        last_seen_at=now,
    )
    db.add(session)
    db.flush()
    AuditRecorder(db).append(
        owner_id=user.id,
        actor_id=user.id,
        action="SessionCreated",
        entity_type="Session",
        entity_id=session.id,
        request_id=_request_id(request),
    )
    db.commit()
    settings = get_settings()
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie(
        settings.session_cookie_name,
        credentials.session_token,
        max_age=max_age,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        credentials.csrf_token,
        max_age=max_age,
        secure=settings.cookie_secure,
        httponly=False,
        samesite="lax",
        path="/",
    )
    return SessionView(
        user=UserView.model_validate(user),
        expires_at=credentials.expires_at,
        csrf_token=credentials.csrf_token,
    )


@router.get("/session", response_model=SessionView)
def current_session(auth: AuthContext = Depends(require_user)) -> SessionView:
    return SessionView(user=UserView.model_validate(auth.user), expires_at=auth.session.expires_at)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_csrf),
    db: DatabaseSession = Depends(get_db),
) -> None:
    auth.session.revoked_at = datetime.now(UTC)
    AuditRecorder(db).append(
        owner_id=auth.user.id,
        actor_id=auth.user.id,
        action="SessionRevoked",
        entity_type="Session",
        entity_id=auth.session.id,
        request_id=_request_id(request),
    )
    db.commit()
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")
