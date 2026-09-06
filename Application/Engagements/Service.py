from Application.Activity.Service import ActivityService
from Application.Users.Repository import session_scope
from .Models import Engagement
from .Repository import EngagementRepository
from .Schemas import EngagementCreate
from Application.Clients.Models import Client
from Application.Common.Enums import ClientStatus
from Application.Users.Models import User
from Application.Settings.Models import WorkspaceSettings


class EngagementService:
    def __init__(self) -> None:
        self.repository = EngagementRepository()

    def list(self, query: str = "", status: str = "") -> list[Engagement]:
        with session_scope() as session:
            return self.repository.list(session, query, status)

    def get(self, engagement_id: int) -> Engagement | None:
        with session_scope() as session:
            return self.repository.get(session, engagement_id)

    def create(self, data: EngagementCreate, actor_id: int) -> Engagement:
        with session_scope() as session:
            client = session.get(Client, data.client_id)
            if not client or client.status != ClientStatus.ACTIVE.value:
                raise ValueError("Select an active client.")
            owner = session.get(User, data.owner_id)
            if not owner or not owner.is_active:
                raise ValueError("Select an active owner.")
            workspace = session.get(WorkspaceSettings, 1)
            if not workspace:
                raise ValueError("Workspace settings are missing.")
            item = Engagement(**data.model_dump(exclude={"currency"}), currency=workspace.currency)
            session.add(item)
            session.flush()
            ActivityService.record(session, actor_id, "Engagement", item.id, "created", f"created engagement {item.name}")
            return item
