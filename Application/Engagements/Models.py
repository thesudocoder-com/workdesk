from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Application.Common.Enums import BillingFrequency, EngagementStatus
from Application.Common.Money import DEFAULT_CURRENCY
from Application.Common.Time import now_utc
from Application.Users.Models import Base


class Engagement(Base):
    __tablename__ = "engagements"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    type: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    contract_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default=DEFAULT_CURRENCY)
    billing_frequency: Mapped[str] = mapped_column(String(30), default=BillingFrequency.ONE_TIME.value)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default=EngagementStatus.ACTIVE.value, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    client = relationship("Client", back_populates="engagements")
    owner = relationship("User")
    projects = relationship("Project", back_populates="engagement")
    milestones = relationship("PaymentMilestone", back_populates="engagement")
    invoices = relationship("Invoice", back_populates="engagement")
