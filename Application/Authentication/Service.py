from __future__ import annotations

from Application.Users.Repository import UserRepository, session_scope
from .Schemas import LoginRequest
from .Security import DUMMY_PASSWORD_HASH, verify_password


class AuthenticationError(ValueError):
    pass


class AuthenticationService:
    def __init__(self, repository: UserRepository | None = None) -> None:
        self.repository = repository or UserRepository()

    def authenticate(self, credentials: LoginRequest):
        with session_scope() as session:
            user = self.repository.get_by_email(session, str(credentials.email))
            if not user:
                verify_password(credentials.password, DUMMY_PASSWORD_HASH)
                raise AuthenticationError("Email or password is incorrect.")
            if not verify_password(credentials.password, user.password_hash):
                raise AuthenticationError("Email or password is incorrect.")
            if not user.is_active:
                raise AuthenticationError("This account has been deactivated. Contact an admin.")
            return user
