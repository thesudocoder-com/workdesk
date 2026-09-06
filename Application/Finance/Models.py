from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Application.Common.Enums import ExpenseCategory, InvoiceStatus, MilestoneStatus
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
    status: Mapped[str] = mapped_column(String(24), default=InvoiceStatus.DRAFT.value, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    client = relationship("Client")
    engagement = relationship("Engagement", back_populates="invoices")
    milestone = relationship("PaymentMilestone", back_populates="invoice")
    payments = relationship("Payment", back_populates="invoice")

    @property
    def amount_paid(self) -> Decimal:
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
