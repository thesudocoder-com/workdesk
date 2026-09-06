from __future__ import annotations

from sqlalchemy import select

from Application.Users.Repository import session_scope
from .Models import WorkspaceSettings
from .Schemas import WorkspaceUpdate


def get_workspace() -> WorkspaceSettings | None:
    with session_scope() as session:
        return session.get(WorkspaceSettings, 1)


def workspace_exists() -> bool:
    with session_scope() as session:
        return session.scalar(select(WorkspaceSettings.id).limit(1)) is not None


def update_workspace(data: WorkspaceUpdate) -> WorkspaceSettings:
    with session_scope() as session:
        workspace = session.get(WorkspaceSettings, 1)
        if not workspace:
            raise ValueError("Workspace setup has not been completed.")
        for key, value in data.model_dump().items():
            if key == "business_email":
                value = str(value) if value else ""
            setattr(workspace, key, value)
        return workspace
