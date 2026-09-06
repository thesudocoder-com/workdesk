from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from Application.Authentication.Security import hash_password
from .Models import User, UserRole
from .Repository import UserRepository, session_scope
from .Schemas import PasswordReset, UserCreate, UserRoleUpdate
from Application.Settings.Models import WorkspaceSettings


class UserConflictError(ValueError):
    pass


class UserRuleError(ValueError):
    pass


class UserService:
    def __init__(self, repository: UserRepository | None = None) -> None:
        self.repository = repository or UserRepository()

    def list_users(self, query: str = "", role: str = "", status: str = "") -> list[User]:
        with session_scope() as session:
            return self.repository.list(session, query, role, status)

    def get_user(self, user_id: int) -> User | None:
        with session_scope() as session:
            return self.repository.get_by_id(session, user_id)

    def create_user(self, data: UserCreate) -> User:
        try:
            with session_scope() as session:
                if not session.get(WorkspaceSettings, 1):
                    raise UserRuleError("Complete browser setup before adding teammates.")
                if self.repository.get_by_email(session, str(data.email)):
                    raise UserConflictError("A user with this email already exists.")
                return self.repository.add(
                    session,
                    User(
                        name=data.name,
                        email=str(data.email).lower(),
                        password_hash=hash_password(data.password),
                        role=data.role.value,
                        must_change_password=True,
                    ),
                )
        except IntegrityError as exc:
            raise UserConflictError("A user with this email already exists.") from exc

    def update_role(self, user_id: int, data: UserRoleUpdate, actor_id: int) -> User:
        with session_scope() as session:
            user = self._require_user(session, user_id)
            if (
                user.role == UserRole.DEVELOPER.value
                and data.role != UserRole.DEVELOPER
                and self.repository.count_active_developers(session) <= 1
            ):
                raise UserRuleError("WorkDesk must always have at least one active Developer.")
            if user.id == actor_id and data.role != UserRole.DEVELOPER:
                raise UserRuleError("You cannot remove your own Developer access.")
            user.role = data.role.value
            user.session_version += 1
            return user

    def toggle_status(self, user_id: int, actor_id: int) -> User:
        with session_scope() as session:
            user = self._require_user(session, user_id)
            if user.id == actor_id and user.is_active:
                raise UserRuleError("You cannot deactivate your own account.")
            if (
                user.role == UserRole.DEVELOPER.value
                and user.is_active
                and self.repository.count_active_developers(session) <= 1
            ):
                raise UserRuleError("WorkDesk must always have at least one active Developer.")
            user.is_active = not user.is_active
            user.session_version += 1
            return user

    def reset_password(self, user_id: int, data: PasswordReset) -> User:
        with session_scope() as session:
            user = self._require_user(session, user_id)
            user.password_hash = hash_password(data.password)
            user.must_change_password = True
            user.session_version += 1
            return user

    def _require_user(self, session, user_id: int) -> User:
        user = self.repository.get_by_id(session, user_id)
        if not user:
            raise UserRuleError("User not found.")
        return user
