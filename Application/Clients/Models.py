from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Application.Common.Enums import ClientStatus
from Application.Common.Time import now_utc
from Application.Users.Models import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    company_name: Mapped[str | None] = mapped_column(String(180))
    primary_email: Mapped[str | None] = mapped_column(String(255), index=True)
    primary_phone: Mapped[str | None] = mapped_column(String(40))
    website: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24), default=ClientStatus.ACTIVE.value, index=True)
    address_line1: Mapped[str | None] = mapped_column(String(180))
    address_line2: Mapped[str | None] = mapped_column(String(180))
    city: Mapped[str | None] = mapped_column(String(100))
    province: Mapped[str | None] = mapped_column(String(80))
    postal_code: Mapped[str | None] = mapped_column(String(16))
    country: Mapped[str] = mapped_column(String(80), default="Canada")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    engagements = relationship("Engagement", back_populates="client")

    @property
    def display_name(self) -> str:
        return self.company_name or self.name

    @property
    def initials(self) -> str:
        return "".join(part[0] for part in self.display_name.split()[:2]).upper()
