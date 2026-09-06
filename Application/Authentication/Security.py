from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from litestar.connection import ASGIConnection
from litestar.middleware.session.client_side import CookieBackendConfig
from litestar.security.session_auth import SessionAuth

from Application.Configurations import settings
from Application.Users.Repository import UserRepository, session_scope


password_hasher = PasswordHasher()
DUMMY_PASSWORD_HASH = password_hasher.hash("workdesk-dummy-password")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hasher.verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


async def retrieve_user_handler(session: dict[str, Any], connection: ASGIConnection) -> Any | None:
    user_id = session.get("user_id")
    if not isinstance(user_id, int):
        return None
    with session_scope() as database_session:
        user = UserRepository().get_by_id(database_session, user_id)
        version = session.get("session_version")
        return user if user and user.is_active and version == user.session_version else None


def get_csrf_token(session: dict[str, Any]) -> str:
    token = session.get("csrf_token")
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def valid_csrf_token(session: dict[str, Any], candidate: str | None) -> bool:
    expected = session.get("csrf_token")
    return isinstance(expected, str) and isinstance(candidate, str) and hmac.compare_digest(expected, candidate)


session_auth = SessionAuth(
    retrieve_user_handler=retrieve_user_handler,
    session_backend_config=CookieBackendConfig(
        secret=hashlib.sha256(settings.session_secret.encode()).digest(),
        key="workdesk_session",
        max_age=60 * 60 * 12,
        httponly=True,
        secure=settings.session_secure,
        samesite="strict",
    ),
    exclude=[r"^/$", r"^/Login$", r"^/Setup$", r"^/Static/.*", r"^/health$"],
)
