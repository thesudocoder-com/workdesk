from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from Application.Users.Models import Base


class WorkspaceSettings(Base):
    __tablename__ = "workspace_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_workspace_settings_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    business_name: Mapped[str] = mapped_column(String(160))
    legal_name: Mapped[str] = mapped_column(String(160), default="")
    business_email: Mapped[str] = mapped_column(String(255), default="")
    business_phone: Mapped[str] = mapped_column(String(60), default="")
    address_line1: Mapped[str] = mapped_column(String(240), default="")
    city: Mapped[str] = mapped_column(String(120), default="")
    region: Mapped[str] = mapped_column(String(120), default="")
    postal_code: Mapped[str] = mapped_column(String(30), default="")
    country: Mapped[str] = mapped_column(String(80), default="")
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    invoice_prefix: Mapped[str] = mapped_column(String(20), default="WD-")
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=15)
    tax_information: Mapped[str] = mapped_column(Text, default="")
    invoice_footer: Mapped[str] = mapped_column(Text, default="Thank you for your business.")
    next_invoice_number: Mapped[int] = mapped_column(Integer, default=1)
