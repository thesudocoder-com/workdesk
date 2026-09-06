from __future__ import annotations

import hmac

from pydantic import BaseModel, EmailStr, Field, model_validator, field_validator
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from Application.Configurations import settings
from Application.Settings.Models import WorkspaceSettings
from Application.Users.Models import User, UserRole
from Application.Users.Repository import session_scope
from .Security import hash_password


class SetupRequest(BaseModel):
    setup_token: str = Field(min_length=1, max_length=512)
    workspace_name: str = Field(min_length=2, max_length=160)
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    password_confirmation: str = Field(min_length=1, max_length=128)

    @field_validator("workspace_name", "name")
    @classmethod
    def normalize(cls, value: str) -> str:
        return " ".join(value.split())

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_confirmation:
            raise ValueError("Passwords do not match.")
        return self


class SetupError(ValueError):
    pass


def owner_exists() -> bool:
    with session_scope() as session:
        return session.scalar(select(User.id).where(User.role == UserRole.DEVELOPER.value).limit(1)) is not None


def initialize_workspace(data: SetupRequest) -> User:
    if not hmac.compare_digest(data.setup_token, settings.setup_token):
        raise SetupError("The setup token is invalid.")
    try:
        with session_scope() as session:
            if settings.database_url.startswith("sqlite"):
                session.execute(text("BEGIN IMMEDIATE"))
            if session.scalar(select(User.id).where(User.role == UserRole.DEVELOPER.value).limit(1)):
                raise SetupError("Workspace setup has already been completed.")
            if session.get(WorkspaceSettings, 1):
                raise SetupError("Workspace setup has already been completed.")
            workspace = WorkspaceSettings(
                id=1,
                business_name=data.workspace_name,
                legal_name=data.workspace_name,
                business_email=str(data.email).lower(),
                timezone="Asia/Kolkata",
                currency="INR",
            )
            owner = User(
                name=data.name,
                email=str(data.email).lower(),
                password_hash=hash_password(data.password),
                role=UserRole.DEVELOPER.value,
                must_change_password=False,
            )
            session.add_all([workspace, owner])
            session.flush()
            return owner
    except IntegrityError as exc:
        raise SetupError("Workspace setup has already been completed.") from exc
