import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from app.core.config import get_settings

password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
_dummy_password_hash = password_hasher.hash("constant-time-dummy-password")


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    candidate_hash = password_hash or _dummy_password_hash
    valid: bool
    try:
        valid = password_hasher.verify(candidate_hash, password)
    except (VerificationError, VerifyMismatchError):
        valid = False
    return valid and password_hash is not None


def _hash_opaque_value(value: str) -> str:
    secret = get_settings().session_hash_secret.get_secret_value().encode()
    return hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()


def hash_session_token(token: str) -> str:
    return _hash_opaque_value(token)


def hash_csrf_token(token: str) -> str:
    return _hash_opaque_value(f"csrf:{token}")


@dataclass(frozen=True, slots=True)
class NewSessionCredentials:
    session_token: str
    session_hash: str
    csrf_token: str
    csrf_hash: str
    expires_at: datetime


def create_session_credentials(now: datetime | None = None) -> NewSessionCredentials:
    issued_at = now or datetime.now(UTC)
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    return NewSessionCredentials(
        session_token=session_token,
        session_hash=hash_session_token(session_token),
        csrf_token=csrf_token,
        csrf_hash=hash_csrf_token(csrf_token),
        expires_at=issued_at + timedelta(hours=get_settings().session_ttl_hours),
    )


class LoginRateLimiter:
    def __init__(self) -> None:
        self._attempts: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> int | None:
        settings = get_settings()
        now = time.monotonic()
        cutoff = now - settings.login_rate_limit_window_seconds
        with self._lock:
            attempts = self._attempts[key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= settings.login_rate_limit_attempts:
                return max(1, int(settings.login_rate_limit_window_seconds - (now - attempts[0])))
        return None

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._attempts[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._attempts.clear()


login_rate_limiter = LoginRateLimiter()


def secure_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())
