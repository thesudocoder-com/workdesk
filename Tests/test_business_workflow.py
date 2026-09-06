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


def test_invoice_draft_rejection_and_deletion(client):
    setup_owner(client)
    step1 = client.get("/Projects/New")
    made_client = client.post("/Projects/New/Client", data={"csrf_token": csrf_from(step1), "name": "Contact Two", "company_name": "Acme Corp", "primary_email": "acme@example.com"}, follow_redirects=False)
    assert made_client.status_code == 303

    step2 = client.get(made_client.headers["location"])
    made_engagement = client.post("/Projects/New/Engagement", data={"csrf_token": csrf_from(step2), "client_id": "1", "name": "Acme Retainer", "type": "Consulting", "contract_value": "8000.00", "billing_frequency": "One Time", "status": "Active"}, follow_redirects=False)
    assert made_engagement.status_code == 303

    # Add a milestone to the engagement
    milestone_form = client.get("/Finance/Milestones/New?engagement_id=1")
    made_milestone = client.post("/Finance/Milestones", data={"csrf_token": csrf_from(milestone_form), "engagement_id": "1", "name": "Milestone 1", "amount": "4000.00", "due_date": "2026-10-01", "status": "Upcoming"}, follow_redirects=False)
    assert made_milestone.status_code == 303

    # Check invoice form does not have Draft option
    invoice_form = client.get("/Finance/Invoices/New?engagement_id=1")
    assert invoice_form.status_code == 200
    assert 'value="Draft"' not in invoice_form.text

    # Attempting to post draft invoice is rejected
    today = today_toronto()
    draft_post = client.post("/Finance/Invoices", data={"csrf_token": csrf_from(invoice_form), "engagement_id": "1", "payment_milestone_id": "1", "issue_date": today.isoformat(), "due_date": (today + timedelta(days=15)).isoformat(), "subtotal": "4000.00", "tax_amount": "0.00", "status": "Draft"})
    assert draft_post.status_code == 422
    assert "must be saved as Sent" in draft_post.text or "Draft invoices are not permitted" in draft_post.text

    # Creating valid invoice without status or with Sent succeeds
    created = client.post("/Finance/Invoices", data={"csrf_token": csrf_from(invoice_form), "engagement_id": "1", "payment_milestone_id": "1", "issue_date": today.isoformat(), "due_date": (today + timedelta(days=15)).isoformat(), "subtotal": "4000.00", "tax_amount": "0.00"}, follow_redirects=False)
    assert created.status_code == 303

    overview = FinanceService().overview()
    assert len(overview["invoices"]) == 1
    inv = overview["invoices"][0]
    assert inv.status == "Sent"

    # Verify milestone is invoiced
    detail_page = client.get("/Engagements/1")
    assert "Invoiced" in detail_page.text

    # Check that Delete invoice is available in Finance table and invoice detail page
    finance_page = client.get("/Finance")
    assert f'/Finance/Invoices/{inv.id}/Delete' in finance_page.text
    assert "Delete invoice" in finance_page.text

    inv_detail = client.get(f"/Finance/Invoices/{inv.id}")
    assert f'/Finance/Invoices/{inv.id}/Delete' in inv_detail.text
    assert "Delete invoice" in inv_detail.text

    # Record payment on invoice
    pay_form = client.get(f"/Finance/Payments/New?invoice_id={inv.id}")
    client.post("/Finance/Payments", data={"csrf_token": csrf_from(pay_form), "invoice_id": str(inv.id), "amount": "2000.00", "paid_at": "2026-09-06T12:00", "payment_method": "Bank Transfer"}, follow_redirects=False)

    # Delete invoice
    delete_resp = client.post(f"/Finance/Invoices/{inv.id}/Delete", data={"csrf_token": csrf_from(inv_detail)}, follow_redirects=False)
    assert delete_resp.status_code == 303
    assert delete_resp.headers["location"] == "/Finance"

    # Verify invoice is deleted
    overview_after = FinanceService().overview()
    assert len(overview_after["invoices"]) == 0
    assert len(overview_after["payments"]) == 0

    # Verify milestone status is restored to Upcoming
    detail_after = client.get("/Engagements/1")
    assert "Upcoming" in detail_after.text

    # Deleting non-existent invoice redirects with error message
    bad_del = client.post("/Finance/Invoices/9999/Delete", data={"csrf_token": csrf_from(finance_page)}, follow_redirects=False)
    assert bad_del.status_code == 303
    assert bad_del.headers["location"] == "/Finance"

    # Deleting with invalid CSRF token redirects with error message
    bad_csrf = client.post("/Finance/Invoices/1/Delete", data={"csrf_token": "invalid_token"}, follow_redirects=False)
    assert bad_csrf.status_code == 303
    assert bad_csrf.headers["location"] == "/Finance"


def test_client_crud_edit_and_delete(client):
    setup_owner(client)
    # 1. Create client
    step1 = client.get("/Clients/New")
    client.post("/Clients", data={"csrf_token": csrf_from(step1), "name": "Alice Contact", "company_name": "Alpha Corp", "primary_email": "alice@alpha.com", "status": "Active"}, follow_redirects=False)

    # 2. Check UI has edit and delete in table and detail
    table_page = client.get("/Clients")
    assert "/Clients/1/Edit" in table_page.text
    assert "/Clients/1/Delete" in table_page.text

    detail_page = client.get("/Clients/1")
    assert "/Clients/1/Edit" in detail_page.text
    assert "/Clients/1/Delete" in detail_page.text

    # 3. Edit client
    edit_page = client.get("/Clients/1/Edit")
    assert edit_page.status_code == 200
    assert "Alpha Corp" in edit_page.text
    update_res = client.post("/Clients/1/Edit", data={"csrf_token": csrf_from(edit_page), "name": "Alice Updated", "company_name": "Alpha Global", "primary_email": "alice@alphaglobal.com", "status": "Active"}, follow_redirects=False)
    assert update_res.status_code == 303
    assert update_res.headers["location"] == "/Clients/1"

    updated_detail = client.get("/Clients/1")
    assert "Alpha Global" in updated_detail.text
    assert "Alice Updated" in updated_detail.text

    # 4. Create child engagement, project, task, milestone, invoice, payment
    eng_page = client.get("/Engagements/New?client_id=1")
    client.post("/Engagements", data={"csrf_token": csrf_from(eng_page), "client_id": "1", "name": "Alpha Retainer", "type": "Consulting", "owner_id": "1", "contract_value": "10000.00", "billing_frequency": "One Time", "status": "Active"}, follow_redirects=False)

    step3 = client.get("/Projects/New?engagement_id=1")
    client.post("/Projects", data={"csrf_token": csrf_from(step3), "engagement_id": "1", "name": "Alpha Site", "owner_id": "1", "status": "Active", "priority": "High"}, follow_redirects=False)

    task_form = client.get("/Tasks/New?project_id=1")
    client.post("/Tasks", data={"csrf_token": csrf_from(task_form), "project_id": "1", "title": "Alpha Task 1", "assigned_to_id": "1", "priority": "Medium", "status": "To Do"}, follow_redirects=False)

    today = today_toronto()
    inv_form = client.get("/Finance/Invoices/New?engagement_id=1")
    client.post("/Finance/Invoices", data={"csrf_token": csrf_from(inv_form), "engagement_id": "1", "issue_date": today.isoformat(), "due_date": (today + timedelta(days=15)).isoformat(), "subtotal": "5000.00", "tax_amount": "0.00"}, follow_redirects=False)

    # 5. Delete client -> cascades everything
    del_res = client.post("/Clients/1/Delete", data={"csrf_token": csrf_from(updated_detail)}, follow_redirects=False)
    assert del_res.status_code == 303
    assert del_res.headers["location"] == "/Clients"

    # Verify everything is gone
    assert client.get("/Clients/1", follow_redirects=False).headers["location"] == "/Clients"
    assert client.get("/Engagements/1", follow_redirects=False).headers["location"] == "/Engagements"
    assert client.get("/Projects/1", follow_redirects=False).headers["location"] == "/Projects"
    assert len(FinanceService().overview()["invoices"]) == 0


def test_engagement_crud_edit_and_delete(client):
    setup_owner(client)
    # Create client
    step1 = client.get("/Clients/New")
    client.post("/Clients", data={"csrf_token": csrf_from(step1), "name": "Bob Contact", "company_name": "Beta LLC", "primary_email": "bob@beta.com", "status": "Active"}, follow_redirects=False)

    # Create engagement
    eng_page = client.get("/Engagements/New?client_id=1")
    client.post("/Engagements", data={"csrf_token": csrf_from(eng_page), "client_id": "1", "name": "Beta Branding", "type": "Consulting", "owner_id": "1", "contract_value": "6000.00", "billing_frequency": "One Time", "status": "Active"}, follow_redirects=False)

    # Check UI has edit and delete in table and detail
    table_page = client.get("/Engagements")
    assert "/Engagements/1/Edit" in table_page.text
    assert "/Engagements/1/Delete" in table_page.text

    detail_page = client.get("/Engagements/1")
    assert "/Engagements/1/Edit" in detail_page.text
    assert "/Engagements/1/Delete" in detail_page.text

    # Edit engagement
    edit_page = client.get("/Engagements/1/Edit")
    assert edit_page.status_code == 200
    assert "Beta Branding" in edit_page.text
    update_res = client.post("/Engagements/1/Edit", data={"csrf_token": csrf_from(edit_page), "client_id": "1", "name": "Beta Rebrand v2", "type": "Consulting", "owner_id": "1", "contract_value": "7500.00", "billing_frequency": "Monthly", "status": "Active"}, follow_redirects=False)
    assert update_res.status_code == 303
    assert update_res.headers["location"] == "/Engagements/1"

    updated_detail = client.get("/Engagements/1")
    assert "Beta Rebrand v2" in updated_detail.text
    assert "₹7,500.00" in updated_detail.text or "7500" in updated_detail.text

    # Create child project and invoice
    step3 = client.get("/Projects/New?engagement_id=1")
    client.post("/Projects", data={"csrf_token": csrf_from(step3), "engagement_id": "1", "name": "Beta Logo", "owner_id": "1", "status": "Active", "priority": "High"}, follow_redirects=False)

    today = today_toronto()
    inv_form = client.get("/Finance/Invoices/New?engagement_id=1")
    client.post("/Finance/Invoices", data={"csrf_token": csrf_from(inv_form), "engagement_id": "1", "issue_date": today.isoformat(), "due_date": (today + timedelta(days=15)).isoformat(), "subtotal": "3000.00", "tax_amount": "0.00"}, follow_redirects=False)

    # Delete engagement -> cascades project and invoice, keeps client
    del_res = client.post("/Engagements/1/Delete", data={"csrf_token": csrf_from(updated_detail)}, follow_redirects=False)
    assert del_res.status_code == 303
    assert del_res.headers["location"] == "/Engagements"

    assert client.get("/Engagements/1", follow_redirects=False).headers["location"] == "/Engagements"
    assert client.get("/Projects/1", follow_redirects=False).headers["location"] == "/Projects"
    assert len(FinanceService().overview()["invoices"]) == 0
    # Client still exists
    assert client.get("/Clients/1").status_code == 200


def test_project_crud_edit_and_delete(client):
    setup_owner(client)
    # Create client and engagement
    step1 = client.get("/Clients/New")
    client.post("/Clients", data={"csrf_token": csrf_from(step1), "name": "Carol Contact", "company_name": "Gamma Inc", "primary_email": "carol@gamma.com", "status": "Active"}, follow_redirects=False)

    eng_page = client.get("/Engagements/New?client_id=1")
    client.post("/Engagements", data={"csrf_token": csrf_from(eng_page), "client_id": "1", "name": "Gamma Dev", "type": "Custom Software", "owner_id": "1", "contract_value": "12000.00", "billing_frequency": "One Time", "status": "Active"}, follow_redirects=False)

    # Create project
    step3 = client.get("/Projects/New?engagement_id=1")
    client.post("/Projects", data={"csrf_token": csrf_from(step3), "engagement_id": "1", "name": "Gamma Backend", "owner_id": "1", "status": "Active", "priority": "High"}, follow_redirects=False)

    # Check UI has edit and delete in table and detail
    table_page = client.get("/Projects")
    assert "/Projects/1/Edit" in table_page.text
    assert "/Projects/1/Delete" in table_page.text

    detail_page = client.get("/Projects/1")
    assert "/Projects/1/Edit" in detail_page.text
    assert "/Projects/1/Delete" in detail_page.text

    # Edit project
    edit_page = client.get("/Projects/1/Edit")
    assert edit_page.status_code == 200
    assert "Gamma Backend" in edit_page.text
    update_res = client.post("/Projects/1/Edit", data={"csrf_token": csrf_from(edit_page), "engagement_id": "1", "name": "Gamma Fullstack", "owner_id": "1", "status": "Active", "priority": "Urgent", "description": "Updated scope"}, follow_redirects=False)
    assert update_res.status_code == 303
    assert update_res.headers["location"] == "/Projects/1"

    updated_detail = client.get("/Projects/1")
    assert "Gamma Fullstack" in updated_detail.text
    assert "Urgent" in updated_detail.text

    # Create task and expense
    task_form = client.get("/Tasks/New?project_id=1")
    client.post("/Tasks", data={"csrf_token": csrf_from(task_form), "project_id": "1", "title": "Setup DB", "assigned_to_id": "1", "priority": "High", "status": "To Do"}, follow_redirects=False)

    exp_form = client.get("/Finance/Expenses/New")
    client.post("/Finance/Expenses", data={"csrf_token": csrf_from(exp_form), "project_id": "1", "vendor": "AWS", "description": "Hosting", "amount": "50.00", "expense_date": "2026-09-06", "category": "Software"}, follow_redirects=False)

    # Delete project -> cascades tasks and expenses, keeps client & engagement
    del_res = client.post("/Projects/1/Delete", data={"csrf_token": csrf_from(updated_detail)}, follow_redirects=False)
    assert del_res.status_code == 303
    assert del_res.headers["location"] == "/Projects"

    assert client.get("/Projects/1", follow_redirects=False).headers["location"] == "/Projects"
    assert client.get("/Engagements/1").status_code == 200
    assert client.get("/Clients/1").status_code == 200



