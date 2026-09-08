from calendar import monthrange
from datetime import UTC, date, datetime
from decimal import Decimal
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from Application.Activity.Service import ActivityService
from Application.Common.Enums import (
    BillingFrequency, InvoiceStatus, MilestoneStatus, OccurrenceStatus, RecurringStatus,
)
from Application.Common.Money import money
from Application.Common.Time import business_timezone, today_toronto
from Application.Engagements.Models import Engagement
from Application.Projects.Models import Project
from Application.Common.Enums import EngagementStatus, ProjectStatus
from Application.Settings.Models import WorkspaceSettings
from Application.Users.Repository import session_scope
from .Models import (
    BillingOccurrence, Expense, FixedFeeAgreement, Instalment, Invoice, InvoiceLine,
    Payment, PaymentAllocation, PaymentMilestone, RecurringService,
)
from .Repository import FinanceRepository
from .Schemas import (
    AgreementCreate, ExpenseCreate, InstalmentCreate, InvoiceCreate, MilestoneCreate,
    PaymentCreate, RecurringServiceCreate, RecurringServiceUpdate,
)


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
                "contracted": sum((item.contract_value + item.adjustment_amount for item in session.scalars(select(FixedFeeAgreement))), Decimal("0")),
                "scheduled": sum((item.amount for item in session.scalars(select(Instalment))), Decimal("0")),
                "recurring_forecast": sum((item.amount for item in session.scalars(select(BillingOccurrence).where(BillingOccurrence.status == OccurrenceStatus.FORECAST.value))), Decimal("0")),
                "recurring_services": list(session.scalars(select(RecurringService).options(
                    selectinload(RecurringService.engagement).selectinload(Engagement.client)
                ).order_by(RecurringService.next_billing_date))),
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
            agreement = session.scalar(select(FixedFeeAgreement).where(
                FixedFeeAgreement.engagement_id == engagement.id,
                FixedFeeAgreement.legacy_source == f"engagement:{engagement.id}",
            ))
            if not agreement:
                agreement = FixedFeeAgreement(
                    engagement_id=engagement.id, name=engagement.name,
                    contract_value=engagement.contract_value, currency=workspace.currency,
                    legacy_source=f"engagement:{engagement.id}",
                )
                session.add(agreement); session.flush()
            session.add(Instalment(
                agreement_id=agreement.id, name=item.name, amount=item.amount,
                currency=item.currency, due_date=item.due_date, sequence=item.sequence,
                status=item.status, legacy_milestone_id=item.id,
            ))
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
            instalment = None
            if milestone:
                instalment = session.scalar(select(Instalment).where(Instalment.legacy_milestone_id == milestone.id))
                if instalment:
                    instalment.invoice_id = invoice.id
            session.add(InvoiceLine(
                invoice_id=invoice.id,
                description=milestone.name if milestone else f"{engagement.name} services",
                quantity=Decimal("1"), unit_price=invoice.subtotal,
                tax_amount=invoice.tax_amount, instalment_id=instalment.id if instalment else None,
            ))
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
            session.add(PaymentAllocation(payment_id=payment.id, invoice_id=invoice.id, amount=payment.amount))
            session.flush(); session.refresh(invoice)
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

    def create_agreement(self, data: AgreementCreate, actor_id: int) -> FixedFeeAgreement:
        with session_scope() as session:
            engagement = session.get(Engagement, data.engagement_id)
            if not engagement:
                raise ValueError("Engagement not found.")
            item = FixedFeeAgreement(**data.model_dump(), currency=engagement.currency)
            session.add(item); session.flush()
            ActivityService.record(session, actor_id, "Engagement", engagement.id, "billing", f"added fixed fee {item.name}")
            return item

    def add_instalment(self, data: InstalmentCreate, actor_id: int) -> Instalment:
        with session_scope() as session:
            agreement = session.get(FixedFeeAgreement, data.agreement_id)
            if not agreement:
                raise ValueError("Agreement not found.")
            new_total = agreement.scheduled_value + data.amount
            if new_total > agreement.expected_scheduled_value:
                raise ValueError("Instalments cannot exceed the contract value plus recorded adjustment.")
            item = Instalment(**data.model_dump(), currency=agreement.currency, agreement=agreement)
            session.add(item); session.flush()
            ActivityService.record(session, actor_id, "Engagement", agreement.engagement_id, "billing", f"added instalment {item.name}")
            return item

    def create_recurring_service(self, data: RecurringServiceCreate, actor_id: int) -> RecurringService:
        with session_scope() as session:
            engagement = session.get(Engagement, data.engagement_id)
            if not engagement:
                raise ValueError("Engagement not found.")
            item = RecurringService(**data.model_dump(), currency=engagement.currency,
                                    next_billing_date=data.start_date)
            session.add(item); session.flush()
            self._materialize_occurrences(session, item, through=data.start_date)
            ActivityService.record(session, actor_id, "Engagement", engagement.id, "billing", f"added recurring service {item.name}")
            return item

    def get_recurring_service(self, service_id: int) -> RecurringService | None:
        with session_scope() as session:
            return session.scalar(select(RecurringService).where(
                RecurringService.id == service_id
            ).options(
                selectinload(RecurringService.engagement).selectinload(Engagement.client),
                selectinload(RecurringService.occurrences).selectinload(BillingOccurrence.invoice),
            ))

    def update_recurring_service(
        self, service_id: int, data: RecurringServiceUpdate, actor_id: int
    ) -> RecurringService:
        with session_scope() as session:
            item = session.get(RecurringService, service_id)
            if not item:
                raise ValueError("Recurring service not found.")
            if data.end_date and data.end_date < item.start_date:
                raise ValueError("End date cannot be before the service start date.")
            for key, value in data.model_dump().items():
                setattr(item, key, value)
            for occurrence in item.occurrences:
                if occurrence.status == OccurrenceStatus.FORECAST.value and not occurrence.invoice_id:
                    occurrence.amount = item.amount
            ActivityService.record(session, actor_id, "Engagement", item.engagement_id,
                                   "billing", f"updated recurring service {item.name}")
            return item

    def set_recurring_status(self, service_id: int, status: RecurringStatus, actor_id: int) -> RecurringService:
        with session_scope() as session:
            item = session.get(RecurringService, service_id)
            if not item:
                raise ValueError("Recurring service not found.")
            if status == RecurringStatus.ACTIVE and item.end_date and item.end_date < today_toronto():
                raise ValueError("Extend the end date before resuming this service.")
            item.status = status.value
            ActivityService.record(session, actor_id, "Engagement", item.engagement_id,
                                   "billing", f"marked recurring service {item.name} {status.value.lower()}")
            return item

    def forecast_recurring(self, through: date) -> int:
        with session_scope() as session:
            count = 0
            services = session.scalars(select(RecurringService).where(
                RecurringService.status == RecurringStatus.ACTIVE.value,
                RecurringService.next_billing_date <= through,
            ))
            for service in services:
                count += self._materialize_occurrences(session, service, through)
            return count

    @staticmethod
    def _materialize_occurrences(session, service: RecurringService, through: date) -> int:
        count = 0
        billing_date = service.next_billing_date
        while billing_date <= through and (not service.end_date or billing_date <= service.end_date):
            exists = session.scalar(select(BillingOccurrence.id).where(
                BillingOccurrence.recurring_service_id == service.id,
                BillingOccurrence.billing_date == billing_date,
            ))
            if not exists:
                session.add(BillingOccurrence(
                    recurring_service_id=service.id, billing_date=billing_date,
                    amount=service.amount, currency=service.currency,
                    status=OccurrenceStatus.FORECAST.value,
                ))
                count += 1
            billing_date = FinanceService._next_date(billing_date, service.frequency, service.interval)
        service.next_billing_date = billing_date
        return count

    @staticmethod
    def _next_date(value: date, frequency: str, interval: int) -> date:
        months = {
            BillingFrequency.MONTHLY.value: 1,
            BillingFrequency.QUARTERLY.value: 3,
            BillingFrequency.ANNUAL.value: 12,
            BillingFrequency.CUSTOM.value: 1,
        }[frequency] * interval
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        return value.replace(year=year, month=month, day=min(value.day, monthrange(year, month)[1]))

    @staticmethod
    def _refresh_overdue(invoices: list[Invoice]) -> None:
        today = today_toronto()
        for invoice in invoices:
            if invoice.due_date < today and invoice.outstanding > 0 and invoice.status not in {InvoiceStatus.DRAFT.value, InvoiceStatus.CANCELLED.value}:
                invoice.status = InvoiceStatus.OVERDUE.value
