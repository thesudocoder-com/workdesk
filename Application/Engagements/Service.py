from sqlalchemy import select

from Application.Activity.Service import ActivityService
from Application.Clients.Models import Client
from Application.Common.Enums import BillingFrequency, ClientStatus
from Application.Finance.Models import (
    Expense, FixedFeeAgreement, Invoice, Payment, PaymentMilestone, RecurringService,
)
from Application.Projects.Models import Project
from Application.Settings.Models import WorkspaceSettings
from Application.Tasks.Models import WorkTask
from Application.Users.Models import User
from Application.Users.Repository import session_scope
from .Models import Engagement
from .Repository import EngagementRepository
from .Schemas import EngagementCreate, EngagementUpdate


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
            if item.contract_value > 0 and item.billing_frequency == BillingFrequency.ONE_TIME.value:
                session.add(FixedFeeAgreement(engagement_id=item.id, name=item.name,
                                              contract_value=item.contract_value, currency=item.currency,
                                              legacy_source=f"engagement:{item.id}"))
            elif item.contract_value > 0 and item.start_date:
                session.add(RecurringService(engagement_id=item.id, name=item.name,
                                             amount=item.contract_value, currency=item.currency,
                                             frequency=item.billing_frequency, start_date=item.start_date,
                                             next_billing_date=item.start_date, end_date=item.end_date,
                                             legacy_source=f"engagement:{item.id}"))
            ActivityService.record(session, actor_id, "Engagement", item.id, "created", f"created engagement {item.name}")
            return item

    def update(self, engagement_id: int, data: EngagementUpdate, actor_id: int) -> Engagement:
        with session_scope() as session:
            item = self.repository.get(session, engagement_id)
            if not item:
                raise ValueError("Engagement not found.")
            client = session.get(Client, data.client_id)
            if not client or client.status != ClientStatus.ACTIVE.value:
                raise ValueError("Select an active client.")
            owner = session.get(User, data.owner_id)
            if not owner or not owner.is_active:
                raise ValueError("Select an active owner.")
            for key, value in data.model_dump().items():
                setattr(item, key, value)
            ActivityService.record(session, actor_id, "Engagement", item.id, "updated", f"updated engagement {item.name}")
            return item

    def delete(self, engagement_id: int, actor_id: int) -> None:
        with session_scope() as session:
            item = self.repository.get(session, engagement_id)
            if not item:
                raise ValueError("Engagement not found.")
            name = item.name
            # Delete child projects and their tasks/expenses
            for project in list(item.projects):
                for task in list(project.tasks):
                    session.delete(task)
                proj_expenses = list(session.scalars(select(Expense).where(Expense.project_id == project.id)))
                for exp in proj_expenses:
                    session.delete(exp)
                session.delete(project)
            # Delete child expenses
            expenses = list(session.scalars(select(Expense).where(Expense.engagement_id == engagement_id)))
            for exp in expenses:
                session.delete(exp)
            # Delete child invoices and payments
            for invoice in list(item.invoices):
                for payment in list(invoice.payments):
                    session.delete(payment)
                session.delete(invoice)
            # Delete child milestones
            for milestone in list(item.milestones):
                session.delete(milestone)
            session.delete(item)
            session.flush()
            ActivityService.record(session, actor_id, "Engagement", engagement_id, "deleted", f"deleted engagement {name}")
