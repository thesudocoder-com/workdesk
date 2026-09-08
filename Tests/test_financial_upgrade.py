from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from Application.Clients.Models import Client, Contact
from Application.Common.Enums import BillingFrequency, EngagementStatus, EngagementType, PaymentMethod
from Application.Engagements.Models import Engagement
from Application.Engagements.Schemas import EngagementCreate
from Application.Engagements.Service import EngagementService
from Application.Finance.Migration import migrate_legacy_finance
from Application.Finance.Models import (
    BillingOccurrence, FixedFeeAgreement, InvoiceLine, PaymentAllocation, RecurringService,
)
from Application.Finance.Schemas import InvoiceCreate, MilestoneCreate, PaymentCreate, RecurringServiceCreate
from Application.Finance.Service import FinanceService
from Application.Users.Repository import session_scope
from Tests.conftest import csrf_from, setup_owner


def test_jkn_flooring_financial_model_and_recurring_forecast(client):
    setup_owner(client)
    with session_scope() as session:
        client_record = Client(name="Kamal", company_name="JKN Flooring", default_currency="CAD")
        session.add(client_record); session.flush()
        session.add(Contact(client_id=client_record.id, name="Kamal", is_primary=True))
        client_id = client_record.id

    engagement = EngagementService().create(EngagementCreate(
        client_id=client_id, name="Website", type=EngagementType.WEBSITE,
        contract_value=Decimal("900.00"), currency="CAD",
        billing_frequency=BillingFrequency.ONE_TIME, owner_id=1,
        status=EngagementStatus.ACTIVE,
    ), actor_id=1)
    finance = FinanceService()
    for sequence, due in enumerate((date(2026, 9, 15), date(2026, 10, 15), date(2026, 11, 15)), 1):
        finance.create_milestone(MilestoneCreate(
            engagement_id=engagement.id, name=f"Instalment {sequence}",
            amount=Decimal("300.00"), due_date=due,
        ), actor_id=1)

    invoice = finance.create_invoice(InvoiceCreate(
        engagement_id=engagement.id, payment_milestone_id=1,
        issue_date=date(2026, 9, 8), due_date=date(2026, 9, 15),
        subtotal=Decimal("300.00"), tax_amount=Decimal("0.00"),
    ), actor_id=1)
    finance.record_payment(PaymentCreate(
        invoice_id=invoice.id, amount=Decimal("300.00"),
        paid_at=datetime(2026, 9, 8, 12, 0), payment_method=PaymentMethod.BANK,
    ), actor_id=1)

    service = finance.create_recurring_service(RecurringServiceCreate(
        engagement_id=engagement.id, name="AI service", amount=Decimal("50.00"),
        frequency=BillingFrequency.QUARTERLY, start_date=date(2026, 1, 15),
    ), actor_id=1)
    finance.forecast_recurring(date(2026, 10, 15))

    with session_scope() as session:
        agreement = session.scalar(select(FixedFeeAgreement).where(
            FixedFeeAgreement.engagement_id == engagement.id).options(
            selectinload(FixedFeeAgreement.instalments)
        ))
        assert agreement.scheduled_value == Decimal("900.00")
        assert agreement.collected_value == Decimal("300.00")
        assert agreement.remaining_balance == Decimal("600.00")
        occurrences = session.scalars(select(BillingOccurrence).where(
            BillingOccurrence.recurring_service_id == service.id).order_by(BillingOccurrence.billing_date)).all()
        assert [item.billing_date for item in occurrences] == [
            date(2026, 1, 15), date(2026, 4, 15), date(2026, 7, 15), date(2026, 10, 15)
        ]
        assert all(item.status == "Forecast" and item.invoice_id is None for item in occurrences)
        assert session.scalar(select(func.count(InvoiceLine.id))) == 1
        assert session.scalar(select(func.count(PaymentAllocation.id))) == 1

    assert finance.overview()["outstanding"] == Decimal("0.00")
    calendar_page = client.get("/Calendar?month=2026-10&client_id=1")
    assert calendar_page.status_code == 200
    assert "October 2026" in calendar_page.text and "AI service" in calendar_page.text

    recurring_page = client.get(f"/Finance/Recurring/{service.id}")
    assert recurring_page.status_code == 200 and "Billing schedule" in recurring_page.text
    paused = client.post(
        f"/Finance/Recurring/{service.id}/Status/pause",
        data={"csrf_token": csrf_from(recurring_page)}, follow_redirects=False,
    )
    assert paused.status_code == 303
    assert FinanceService().get_recurring_service(service.id).status == "Paused"

    edit_page = client.get(f"/Finance/Recurring/{service.id}/Edit")
    updated = client.post(f"/Finance/Recurring/{service.id}/Edit", data={
        "csrf_token": csrf_from(edit_page), "name": "AI support service",
        "amount": "60.00", "tax_rate": "0.00", "billing_timing": "Advance",
    }, follow_redirects=False)
    assert updated.status_code == 303
    updated_service = FinanceService().get_recurring_service(service.id)
    assert updated_service.name == "AI support service" and updated_service.amount == Decimal("60.00")


def test_dashboard_shows_workspace_local_time_not_raw_timezone(client):
    setup_owner(client)
    settings_page = client.get("/Settings")
    saved = client.post("/Settings", data={
        "csrf_token": csrf_from(settings_page), "business_name": "Test Studio",
        "timezone": "America/New_York", "currency": "CAD", "invoice_prefix": "WD-",
        "payment_terms_days": "15",
    }, follow_redirects=False)
    assert saved.status_code == 303
    dashboard = client.get("/Dashboard")
    assert 'data-timezone="America/New_York"' in dashboard.text
    assert "· America/New_York</span>" not in dashboard.text
    assert '· <time data-workspace-clock data-timezone="America/New_York">' in dashboard.text
    assert "data-workspace-clock" in dashboard.text


def test_finance_migration_is_idempotent(client):
    setup_owner(client)
    with session_scope() as session:
        first = migrate_legacy_finance(session, apply=True)
        second = migrate_legacy_finance(session, apply=True)
        assert all(value == 0 for value in second.to_dict().values())
