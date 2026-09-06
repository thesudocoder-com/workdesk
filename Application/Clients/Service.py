from sqlalchemy import select
from sqlalchemy.orm import selectinload

from Application.Activity.Models import Activity
from Application.Activity.Service import ActivityService
from Application.Engagements.Models import Engagement
from Application.Finance.Models import Expense, Invoice, Payment
from Application.Projects.Models import Project
from Application.Tasks.Models import WorkTask
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

    def delete(self, client_id: int, actor_id: int) -> None:
        with session_scope() as session:
            client = self.repository.get(session, client_id)
            if not client:
                raise ValueError("Client not found.")
            display_name = client.display_name
            invoices = list(session.scalars(select(Invoice).where(Invoice.client_id == client_id).options(selectinload(Invoice.payments))))
            for invoice in invoices:
                for payment in list(invoice.payments):
                    session.delete(payment)
                session.delete(invoice)
            for engagement in list(client.engagements):
                for project in list(engagement.projects):
                    for task in list(project.tasks):
                        session.delete(task)
                    expenses = list(session.scalars(select(Expense).where(Expense.project_id == project.id)))
                    for exp in expenses:
                        session.delete(exp)
                    session.delete(project)
                eng_expenses = list(session.scalars(select(Expense).where(Expense.engagement_id == engagement.id)))
                for exp in eng_expenses:
                    session.delete(exp)
                for milestone in list(engagement.milestones):
                    session.delete(milestone)
                session.delete(engagement)
            session.delete(client)
            session.flush()
            ActivityService.record(session, actor_id, "Client", client_id, "deleted", f"deleted client {display_name}")

