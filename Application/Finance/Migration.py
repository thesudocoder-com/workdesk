from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from Application.Clients.Models import Client, Contact
from Application.Common.Enums import BillingFrequency
from Application.Engagements.Models import Engagement
from .Models import (
    FixedFeeAgreement, Instalment, Invoice, InvoiceLine, MigrationReview, Payment,
    PaymentAllocation, RecurringService,
)


@dataclass
class MigrationReport:
    contacts: int = 0
    agreements: int = 0
    instalments: int = 0
    recurring_services: int = 0
    invoice_lines: int = 0
    allocations: int = 0
    reviews: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def migrate_legacy_finance(session: Session, *, apply: bool = False) -> MigrationReport:
    """Build normalized records from legacy sources; safe to preview and rerun."""
    report = MigrationReport()

    def add(item, counter: str) -> None:
        setattr(report, counter, getattr(report, counter) + 1)
        if apply:
            session.add(item)
            session.flush()

    def review(source_type: str, source_id: int, reason: str, details: str) -> None:
        existing = session.scalar(select(MigrationReview).where(
            MigrationReview.source_type == source_type,
            MigrationReview.source_id == source_id,
            MigrationReview.reason == reason,
        ))
        if not existing:
            add(MigrationReview(source_type=source_type, source_id=source_id, reason=reason, details=details), "reviews")

    for client in session.scalars(select(Client).order_by(Client.id)):
        source = f"client:{client.id}:primary"
        if session.scalar(select(Contact.id).where(Contact.legacy_source == source)):
            continue
        if client.company_name and client.name.strip().casefold() != client.company_name.strip().casefold():
            add(Contact(client_id=client.id, name=client.name, email=client.primary_email,
                        phone=client.primary_phone, is_primary=True, legacy_source=source), "contacts")
        elif client.primary_email or client.primary_phone:
            review("client", client.id, "ambiguous-primary-contact",
                   "Client contact details exist, but the legacy name cannot safely be classified as a person.")

    for engagement in session.scalars(select(Engagement).order_by(Engagement.id)):
        source = f"engagement:{engagement.id}"
        if engagement.billing_frequency == BillingFrequency.ONE_TIME.value and engagement.contract_value > 0:
            agreement = session.scalar(select(FixedFeeAgreement).where(FixedFeeAgreement.legacy_source == source))
            if not agreement:
                agreement = FixedFeeAgreement(
                    engagement_id=engagement.id, name=engagement.name,
                    contract_value=engagement.contract_value, currency=engagement.currency,
                    legacy_source=source,
                )
                add(agreement, "agreements")
            for milestone in engagement.milestones:
                if session.scalar(select(Instalment.id).where(Instalment.legacy_milestone_id == milestone.id)):
                    continue
                invoice = milestone.invoice
                add(Instalment(
                    agreement_id=agreement.id if apply else 0, name=milestone.name,
                    amount=milestone.amount, currency=milestone.currency, due_date=milestone.due_date,
                    sequence=milestone.sequence, status=milestone.status,
                    invoice_id=invoice.id if invoice else None, legacy_milestone_id=milestone.id,
                ), "instalments")
        elif engagement.billing_frequency != BillingFrequency.ONE_TIME.value and engagement.contract_value > 0:
            if not engagement.start_date:
                review("engagement", engagement.id, "missing-recurrence-start",
                       "A recurring legacy engagement has no start date; no date was invented.")
            elif not session.scalar(select(RecurringService.id).where(RecurringService.legacy_source == source)):
                add(RecurringService(
                    engagement_id=engagement.id, name=engagement.name, amount=engagement.contract_value,
                    currency=engagement.currency, frequency=engagement.billing_frequency,
                    start_date=engagement.start_date, next_billing_date=engagement.start_date,
                    end_date=engagement.end_date, legacy_source=source,
                ), "recurring_services")

    for invoice in session.scalars(select(Invoice).order_by(Invoice.id)):
        source = f"invoice:{invoice.id}:legacy-summary"
        if not session.scalar(select(InvoiceLine.id).where(InvoiceLine.invoice_id == invoice.id)):
            add(InvoiceLine(invoice_id=invoice.id, description=f"Legacy invoice {invoice.invoice_number}",
                            quantity=Decimal("1"), unit_price=invoice.subtotal,
                            tax_amount=invoice.tax_amount, legacy_source=source), "invoice_lines")

    for payment in session.scalars(select(Payment).order_by(Payment.id)):
        source = f"payment:{payment.id}:invoice:{payment.invoice_id}"
        if not session.scalar(select(PaymentAllocation.id).where(PaymentAllocation.payment_id == payment.id)):
            add(PaymentAllocation(payment_id=payment.id, invoice_id=payment.invoice_id,
                                  amount=payment.amount, legacy_source=source), "allocations")

    if apply:
        session.flush()
    return report
