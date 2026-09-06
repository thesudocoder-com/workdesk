from datetime import timedelta

from Tests.conftest import csrf_from, setup_owner
from Application.Common.Time import today_toronto
from Application.Finance.Service import FinanceService


def test_guided_workflow_updates_dashboard_and_finance(client):
    setup_owner(client)
    step1 = client.get("/Projects/New")
    made_client = client.post("/Projects/New/Client", data={"csrf_token": csrf_from(step1), "name": "Primary Contact", "company_name": "Customer Company", "primary_email": "contact@example.com"}, follow_redirects=False)
    assert made_client.headers["location"] == "/Projects/New?client_id=1"

    step2 = client.get(made_client.headers["location"])
    made_engagement = client.post("/Projects/New/Engagement", data={"csrf_token": csrf_from(step2), "client_id": "1", "name": "Support Retainer", "type": "Consulting", "contract_value": "5000.00", "billing_frequency": "One Time", "status": "Active"}, follow_redirects=False)
    assert made_engagement.headers["location"] == "/Projects/New?engagement_id=1"

    step3 = client.get(made_engagement.headers["location"])
    made_project = client.post("/Projects", data={"csrf_token": csrf_from(step3), "engagement_id": "1", "name": "Customer Launch", "owner_id": "1", "status": "Active", "priority": "High"}, follow_redirects=False)
    assert made_project.headers["location"] == "/Projects/1"
    dashboard = client.get("/Dashboard")
    assert "Customer Launch" in dashboard.text and "Open projects" in dashboard.text

    today = today_toronto()
    invoice_form = client.get("/Finance/Invoices/New?engagement_id=1")
    created = client.post("/Finance/Invoices", data={"csrf_token": csrf_from(invoice_form), "engagement_id": "1", "issue_date": today.isoformat(), "due_date": (today + timedelta(days=15)).isoformat(), "subtotal": "1000.00", "tax_amount": "180.00", "status": "Sent"}, follow_redirects=False)
    assert created.status_code == 303
    invoice = FinanceService().overview()["invoices"][0]
    assert invoice.invoice_number.endswith("0001")
    invoice_page = client.get(f"/Finance/Invoices/{invoice.id}")
    assert invoice_page.status_code == 200 and "Record payment" in invoice_page.text
    assert f'/Finance/Invoices/{invoice.id}/Download' in invoice_page.text

    download = client.get(f"/Finance/Invoices/{invoice.id}/Download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/pdf")
    assert "attachment" in download.headers["content-disposition"]
    assert download.content.startswith(b"%PDF-")

    payment_form = client.get(f"/Finance/Payments/New?invoice_id={invoice.id}")
    payment = client.post("/Finance/Payments", data={"csrf_token": csrf_from(payment_form), "invoice_id": str(invoice.id), "amount": "1180.00", "paid_at": "2026-09-06T12:00", "payment_method": "Bank Transfer"}, follow_redirects=False)
    assert payment.status_code == 303
    finance = client.get("/Finance")
    assert "Customer Company" in finance.text and "₹1,180.00 INR" in finance.text and "Paid" in finance.text
    reports = client.get("/Reports")
    assert reports.status_code == 200
    assert "Customer Company" in reports.text and "Total collected" in reports.text


def test_forged_references_are_form_errors(client):
    setup_owner(client)
    wizard = client.get("/Projects/New")
    forged = client.post("/Projects", data={"csrf_token": csrf_from(wizard), "engagement_id": "999", "name": "Forged Project", "owner_id": "999", "status": "Active", "priority": "Medium"})
    assert forged.status_code == 422
    assert "active engagement" in forged.text.lower() or "no longer" in forged.text.lower()

    invoice_form = client.get("/Finance/Invoices/New")
    invoice = client.post("/Finance/Invoices", data={"csrf_token": csrf_from(invoice_form), "engagement_id": "999", "issue_date": "2026-09-06", "due_date": "2026-09-20", "subtotal": "10", "tax_amount": "0", "status": "Sent"})
    assert invoice.status_code == 422
