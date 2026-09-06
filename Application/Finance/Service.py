from datetime import UTC, datetime
from decimal import Decimal
from sqlalchemy import update

from Application.Activity.Service import ActivityService
from Application.Common.Enums import InvoiceStatus, MilestoneStatus
from Application.Common.Money import money
from Application.Common.Time import business_timezone, today_toronto
from Application.Engagements.Models import Engagement
from Application.Projects.Models import Project
from Application.Common.Enums import EngagementStatus, ProjectStatus
from Application.Settings.Models import WorkspaceSettings
from Application.Users.Repository import session_scope
from .Models import Expense, Invoice, Payment, PaymentMilestone
from .Repository import FinanceRepository
from .Schemas import ExpenseCreate, InvoiceCreate, MilestoneCreate, PaymentCreate


class FinanceService:
    def __init__(self) -> None:
        self.repository = FinanceRepository()

    def overview(self, status: str = "") -> dict:
        with session_scope() as session:
            invoices = self.repository.invoices(session, status)
            all_invoices = self.repository.invoices(session)
            payments = self.repository.payments(session)
            expenses = self.repository.expenses(session)
            self._refresh_overdue(all_invoices)
            today = today_toronto()
            return {
                "invoices": invoices,
                "payments": payments,
                "expenses": expenses,
                "outstanding": sum((item.outstanding for item in all_invoices if item.status != InvoiceStatus.CANCELLED.value), Decimal("0")),
                "overdue": sum((item.outstanding for item in all_invoices if item.status == InvoiceStatus.OVERDUE.value), Decimal("0")),
                "paid_month": sum((item.amount for item in payments if not item.is_void and item.paid_at.date().month == today.month and item.paid_at.date().year == today.year), Decimal("0")),
                "expense_month": sum((item.amount for item in expenses if item.expense_date.month == today.month and item.expense_date.year == today.year), Decimal("0")),
            }

    def get_invoice(self, invoice_id: int) -> Invoice | None:
        with session_scope() as session:
            return self.repository.invoice(session, invoice_id)

    def create_milestone(self, data: MilestoneCreate, actor_id: int) -> PaymentMilestone:
        with session_scope() as session:
            if data.status not in {MilestoneStatus.UPCOMING, MilestoneStatus.DUE}:
                raise ValueError("New milestones must be upcoming or due.")
            engagement = session.get(Engagement, data.engagement_id)
            if not engagement or engagement.status != EngagementStatus.ACTIVE.value:
                raise ValueError("Select an active engagement.")
            workspace = session.get(WorkspaceSettings, 1)
            item = PaymentMilestone(**data.model_dump(), currency=workspace.currency)
            session.add(item); session.flush()
            ActivityService.record(session, actor_id, "Engagement", item.engagement_id, "billing", f"added milestone {item.name}")
            return item

    def create_invoice(self, data: InvoiceCreate, actor_id: int) -> Invoice:
        with session_scope() as session:
            if data.status != InvoiceStatus.SENT:
                raise ValueError("New invoices must be saved as Sent.")
            engagement = session.get(Engagement, data.engagement_id)
            if not engagement or engagement.status != EngagementStatus.ACTIVE.value:
                raise ValueError("Select an active engagement.")
            workspace = session.get(WorkspaceSettings, 1)
            if not workspace:
                raise ValueError("Workspace settings are missing.")
            sequence = session.scalar(
                update(WorkspaceSettings)
                .where(WorkspaceSettings.id == 1)
                .values(next_invoice_number=WorkspaceSettings.next_invoice_number + 1)
                .returning(WorkspaceSettings.next_invoice_number)
            ) - 1
            milestone = None
            if data.payment_milestone_id:
                milestone = session.get(PaymentMilestone, data.payment_milestone_id)
                if not milestone or milestone.engagement_id != engagement.id or milestone.invoice:
                    raise ValueError("Select an unused milestone from this engagement.")
                milestone.status = MilestoneStatus.INVOICED.value
            invoice = Invoice(
                **data.model_dump(),
                client_id=engagement.client_id,
                invoice_number=f"{workspace.invoice_prefix}{today_toronto().year}-{sequence:04d}",
                currency=workspace.currency,
                total=money(data.subtotal + data.tax_amount),
            )
            session.add(invoice); session.flush()
            ActivityService.record(session, actor_id, "Invoice", invoice.id, "created", f"created {invoice.invoice_number}")
            return invoice

    def delete_invoice(self, invoice_id: int, actor_id: int) -> None:
        with session_scope() as session:
            invoice = self.repository.invoice(session, invoice_id)
            if not invoice:
                raise ValueError("Invoice not found.")
            invoice_number = invoice.invoice_number
            if invoice.milestone:
                milestone = invoice.milestone
                today = today_toronto()
                if milestone.due_date and milestone.due_date < today:
                    milestone.status = MilestoneStatus.DUE.value
                else:
                    milestone.status = MilestoneStatus.UPCOMING.value
                invoice.milestone = None
                invoice.payment_milestone_id = None
            for payment in list(invoice.payments):
                session.delete(payment)
            session.delete(invoice)
            session.flush()
            ActivityService.record(session, actor_id, "Invoice", invoice_id, "deleted", f"deleted invoice {invoice_number}")

    def record_payment(self, data: PaymentCreate, actor_id: int) -> Payment:
        with session_scope() as session:
            invoice = self.repository.invoice(session, data.invoice_id)
            if not invoice:
                raise ValueError("Invoice not found.")
            if invoice.status in {InvoiceStatus.DRAFT.value, InvoiceStatus.CANCELLED.value, InvoiceStatus.PAID.value} or invoice.outstanding <= 0:
                raise ValueError("This invoice has no outstanding balance.")
            if money(data.amount) > invoice.outstanding:
                raise ValueError("Payment cannot exceed the outstanding invoice balance.")
            paid_at = data.paid_at
            if paid_at.tzinfo is None:
                paid_at = paid_at.replace(tzinfo=business_timezone()).astimezone(UTC)
            payment = Payment(**data.model_dump(exclude={"paid_at", "invoice_id"}), paid_at=paid_at, invoice=invoice, currency=invoice.currency, received_by_id=actor_id)
            session.add(payment); session.flush(); session.refresh(invoice)
            invoice.status = InvoiceStatus.PAID.value if invoice.outstanding <= 0 else InvoiceStatus.PARTIALLY_PAID.value
            if invoice.status == InvoiceStatus.PAID.value and invoice.milestone:
                invoice.milestone.status = MilestoneStatus.PAID.value
            ActivityService.record(session, actor_id, "Invoice", invoice.id, "payment", f"recorded {money(payment.amount)} {invoice.currency} on {invoice.invoice_number}")
            return payment

    def add_expense(self, data: ExpenseCreate, actor_id: int) -> Expense:
        with session_scope() as session:
            engagement = session.get(Engagement, data.engagement_id) if data.engagement_id else None
            project = session.get(Project, data.project_id) if data.project_id else None
            if data.engagement_id and not engagement:
                raise ValueError("Selected engagement was not found.")
            if data.project_id and not project:
                raise ValueError("Selected project was not found.")
            if project and engagement and project.engagement_id != engagement.id:
                raise ValueError("The selected project does not belong to that engagement.")
            if project and project.status == ProjectStatus.CANCELLED.value:
                raise ValueError("Cancelled projects cannot receive new expenses.")
            workspace = session.get(WorkspaceSettings, 1)
            expense = Expense(**data.model_dump(), paid_by_id=actor_id, currency=workspace.currency)
            session.add(expense); session.flush()
            ActivityService.record(session, actor_id, "Expense", expense.id, "created", f"recorded expense {expense.vendor}")
            return expense

    @staticmethod
    def _refresh_overdue(invoices: list[Invoice]) -> None:
        today = today_toronto()
        for invoice in invoices:
            if invoice.due_date < today and invoice.outstanding > 0 and invoice.status not in {InvoiceStatus.DRAFT.value, InvoiceStatus.CANCELLED.value}:
                invoice.status = InvoiceStatus.OVERDUE.value
