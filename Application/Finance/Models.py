from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Application.Common.Enums import (
    AgreementStatus, BillingFrequency, BillingTiming, ExpenseCategory, InvoiceStatus,
    MilestoneStatus, OccurrenceStatus, RecurringStatus,
)
from Application.Common.Money import DEFAULT_CURRENCY, ZERO
from Application.Common.Time import now_utc
from Application.Users.Models import Base


class PaymentMilestone(Base):
    __tablename__ = "payment_milestones"

    id: Mapped[int] = mapped_column(primary_key=True)
    engagement_id: Mapped[int] = mapped_column(ForeignKey("engagements.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default=DEFAULT_CURRENCY)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    sequence: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(24), default=MilestoneStatus.UPCOMING.value, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    engagement = relationship("Engagement", back_populates="milestones")
    invoice = relationship("Invoice", back_populates="milestone", uselist=False)


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    engagement_id: Mapped[int] = mapped_column(ForeignKey("engagements.id"), index=True)
    payment_milestone_id: Mapped[int | None] = mapped_column(ForeignKey("payment_milestones.id"), unique=True)
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=ZERO)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default=DEFAULT_CURRENCY)
    status: Mapped[str] = mapped_column(String(24), default=InvoiceStatus.SENT.value, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    client = relationship("Client")
    engagement = relationship("Engagement", back_populates="invoices")
    milestone = relationship("PaymentMilestone", back_populates="invoice")
    payments = relationship("Payment", back_populates="invoice")
    lines = relationship("InvoiceLine", back_populates="invoice", lazy="selectin", cascade="all, delete-orphan", passive_deletes=True)
    allocations = relationship("PaymentAllocation", back_populates="invoice", lazy="selectin", cascade="all, delete-orphan", passive_deletes=True)

    @property
    def amount_paid(self) -> Decimal:
        if self.allocations:
            return sum((allocation.amount for allocation in self.allocations if not allocation.payment.is_void), ZERO)
        return sum((payment.amount for payment in self.payments if not payment.is_void), ZERO)

    @property
    def outstanding(self) -> Decimal:
        return max(self.total - self.amount_paid, ZERO)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default=DEFAULT_CURRENCY)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payment_method: Mapped[str] = mapped_column(String(40))
    reference: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    received_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    is_void: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    invoice = relationship("Invoice", back_populates="payments")
    allocations = relationship("PaymentAllocation", back_populates="payment", lazy="selectin", cascade="all, delete-orphan", passive_deletes=True)
    received_by = relationship("User")


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    engagement_id: Mapped[int | None] = mapped_column(ForeignKey("engagements.id"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True)
    category: Mapped[str] = mapped_column(String(40), default=ExpenseCategory.OTHER.value, index=True)
    vendor: Mapped[str] = mapped_column(String(140), index=True)
    description: Mapped[str] = mapped_column(String(240))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default=DEFAULT_CURRENCY)
    expense_date: Mapped[date] = mapped_column(Date, index=True)
    paid_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    engagement = relationship("Engagement")
    project = relationship("Project")
    paid_by = relationship("User")


class FixedFeeAgreement(Base):
    __tablename__ = "fixed_fee_agreements"

    id: Mapped[int] = mapped_column(primary_key=True)
    engagement_id: Mapped[int] = mapped_column(ForeignKey("engagements.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    contract_value: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    adjustment_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=ZERO)
    adjustment_reason: Mapped[str | None] = mapped_column(String(240))
    currency: Mapped[str] = mapped_column(String(3), default=DEFAULT_CURRENCY)
    status: Mapped[str] = mapped_column(String(24), default=AgreementStatus.ACTIVE.value, index=True)
    legacy_source: Mapped[str | None] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    engagement = relationship("Engagement", back_populates="agreements")
    instalments = relationship("Instalment", back_populates="agreement", order_by="Instalment.sequence", cascade="all, delete-orphan", passive_deletes=True)

    @property
    def scheduled_value(self) -> Decimal:
        return sum((item.amount for item in self.instalments), ZERO)

    @property
    def expected_scheduled_value(self) -> Decimal:
        return self.contract_value + self.adjustment_amount

    @property
    def collected_value(self) -> Decimal:
        return sum((item.paid_amount for item in self.instalments), ZERO)

    @property
    def remaining_balance(self) -> Decimal:
        return max(self.expected_scheduled_value - self.collected_value, ZERO)


class Instalment(Base):
    __tablename__ = "instalments"

    id: Mapped[int] = mapped_column(primary_key=True)
    agreement_id: Mapped[int] = mapped_column(ForeignKey("fixed_fee_agreements.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default=DEFAULT_CURRENCY)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    sequence: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(24), default=MilestoneStatus.UPCOMING.value, index=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), index=True)
    legacy_milestone_id: Mapped[int | None] = mapped_column(ForeignKey("payment_milestones.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    agreement = relationship("FixedFeeAgreement", back_populates="instalments")
    invoice = relationship("Invoice")
    legacy_milestone = relationship("PaymentMilestone")

    @property
    def paid_amount(self) -> Decimal:
        return min(self.invoice.amount_paid, self.amount) if self.invoice else ZERO


class RecurringService(Base):
    __tablename__ = "recurring_services"

    id: Mapped[int] = mapped_column(primary_key=True)
    engagement_id: Mapped[int] = mapped_column(ForeignKey("engagements.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default=DEFAULT_CURRENCY)
    frequency: Mapped[str] = mapped_column(String(30), default=BillingFrequency.MONTHLY.value)
    interval: Mapped[int] = mapped_column(default=1)
    start_date: Mapped[date] = mapped_column(Date)
    next_billing_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default=RecurringStatus.ACTIVE.value, index=True)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(7, 4), default=ZERO)
    billing_timing: Mapped[str] = mapped_column(String(16), default=BillingTiming.ADVANCE.value)
    legacy_source: Mapped[str | None] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    engagement = relationship("Engagement", back_populates="recurring_services")
    occurrences = relationship("BillingOccurrence", back_populates="service", order_by="BillingOccurrence.billing_date", cascade="all, delete-orphan", passive_deletes=True)


class BillingOccurrence(Base):
    __tablename__ = "billing_occurrences"
    __table_args__ = (UniqueConstraint("recurring_service_id", "billing_date", name="uq_occurrence_service_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    recurring_service_id: Mapped[int] = mapped_column(ForeignKey("recurring_services.id", ondelete="CASCADE"), index=True)
    billing_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default=DEFAULT_CURRENCY)
    status: Mapped[str] = mapped_column(String(24), default=OccurrenceStatus.FORECAST.value, index=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    service = relationship("RecurringService", back_populates="occurrences")
    invoice = relationship("Invoice")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(String(240))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=ZERO)
    instalment_id: Mapped[int | None] = mapped_column(ForeignKey("instalments.id"), index=True)
    billing_occurrence_id: Mapped[int | None] = mapped_column(ForeignKey("billing_occurrences.id"), index=True)
    legacy_source: Mapped[str | None] = mapped_column(String(80), unique=True)
    invoice = relationship("Invoice", back_populates="lines")

    @property
    def subtotal(self) -> Decimal:
        return self.quantity * self.unit_price


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"
    __table_args__ = (UniqueConstraint("payment_id", "invoice_id", name="uq_payment_invoice_allocation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    legacy_source: Mapped[str | None] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    payment = relationship("Payment", back_populates="allocations")
    invoice = relationship("Invoice", back_populates="allocations")


class MigrationReview(Base):
    __tablename__ = "migration_reviews"
    __table_args__ = (UniqueConstraint("source_type", "source_id", "reason", name="uq_migration_review"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[int] = mapped_column(index=True)
    reason: Mapped[str] = mapped_column(String(240))
    details: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
