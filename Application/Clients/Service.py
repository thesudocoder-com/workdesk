from sqlalchemy import select
from sqlalchemy.orm import selectinload

from Application.Activity.Models import Activity
from Application.Activity.Service import ActivityService
from Application.Finance.Models import Invoice
from Application.Projects.Models import Project
from Application.Users.Repository import session_scope
from .Models import Client
from .Repository import ClientRepository
from .Schemas import ClientCreate, ClientUpdate


class ClientService:
    def __init__(self) -> None:
        self.repository = ClientRepository()

    def list(self, query: str = "", status: str = "") -> list[Client]:
        with session_scope() as session:
            return self.repository.list(session, query, status)

    def get(self, client_id: int) -> Client | None:
        with session_scope() as session:
            return self.repository.get(session, client_id)

    def detail(self, client_id: int) -> dict | None:
        with session_scope() as session:
            client = self.repository.get(session, client_id)
            if not client:
                return None
            invoices = list(
                session.scalars(
                    select(Invoice).where(Invoice.client_id == client_id).options(selectinload(Invoice.payments))
                )
            )
            projects = list(
                session.scalars(
                    select(Project)
                    .where(Project.engagement.has(client_id=client_id))
                    .options(selectinload(Project.owner), selectinload(Project.engagement))
                )
            )
            activity = list(
                session.scalars(
                    select(Activity)
                    .where(Activity.entity_type == "Client", Activity.entity_id == client_id)
                    .options(selectinload(Activity.user))
                    .order_by(Activity.created_at.desc())
                    .limit(8)
                )
            )
            return {
                "client": client,
                "invoices": invoices,
                "projects": projects,
                "lifetime_revenue": sum((item.amount_paid for item in invoices), 0),
                "outstanding": sum((item.outstanding for item in invoices), 0),
                "activity": activity,
            }

    def create(self, data: ClientCreate, actor_id: int) -> Client:
        with session_scope() as session:
            client = Client(**data.model_dump())
            session.add(client)
            session.flush()
            ActivityService.record(session, actor_id, "Client", client.id, "created", f"created {client.display_name}")
            return client

    def update(self, client_id: int, data: ClientUpdate, actor_id: int) -> Client:
        with session_scope() as session:
            client = self.repository.get(session, client_id)
            if not client:
                raise ValueError("Client not found.")
            for key, value in data.model_dump().items():
                setattr(client, key, value)
            ActivityService.record(session, actor_id, "Client", client.id, "updated", f"updated {client.display_name}")
            return client
