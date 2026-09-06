from Tests.conftest import csrf_from, login, setup_owner


def test_fresh_install_setup_is_protected_and_locks(client):
    assert client.get("/", follow_redirects=False).headers["location"] == "/Setup"
    page = client.get("/Setup")
    invalid = client.post("/Setup", data={"csrf_token": csrf_from(page), "setup_token": "wrong", "workspace_name": "Studio", "name": "Owner", "email": "owner@example.com", "password": "long-password-1", "password_confirmation": "long-password-1"})
    assert invalid.status_code == 422 and "setup token is invalid" in invalid.text
    mismatch = client.post("/Setup", data={"csrf_token": csrf_from(invalid), "setup_token": "development-setup-token", "workspace_name": "Studio", "name": "Owner", "email": "owner@example.com", "password": "long-password-1", "password_confirmation": "different-password"})
    assert mismatch.status_code == 422 and "Passwords do not match" in mismatch.text
    setup_owner(client)
    locked = client.get("/Setup", follow_redirects=False)
    assert locked.status_code == 303 and locked.headers["location"] == "/Login"


def test_temporary_password_change_is_forced(client):
    setup_owner(client)
    users = client.get("/Users/New")
    assert client.post("/Users", data={"csrf_token": csrf_from(users), "name": "Project Teammate", "email": "teammate@example.com", "role": "Team Member", "password": "temporary-password", "password_confirmation": "temporary-password"}, follow_redirects=False).status_code == 303
    logout_page = client.get("/Account/Password")
    client.post("/Logout", data={"csrf_token": csrf_from(logout_page)})
    assert login(client, "teammate@example.com", "temporary-password").headers["location"] == "/Account/Password"
    assert client.get("/Dashboard", follow_redirects=False).headers["location"] == "/Account/Password"
    form = client.get("/Account/Password")
    assert "Temporary password" in form.text
    assert 'id="new-account-password"' in form.text
    mismatch = client.post("/Account/Password", data={"csrf_token": csrf_from(form), "current_password": "temporary-password", "password": "permanent-password", "password_confirmation": "different-password"})
    assert mismatch.status_code == 422 and "New passwords do not match" in mismatch.text
    changed = client.post("/Account/Password", data={"csrf_token": csrf_from(form), "current_password": "temporary-password", "password": "permanent-password", "password_confirmation": "permanent-password"}, follow_redirects=False)
    assert changed.headers["location"] == "/Dashboard"
    assert client.get("/Dashboard").status_code == 200


def test_prerequisites_modal_errors_and_settings(client):
    setup_owner(client)
    for path in ("/Dashboard", "/Clients", "/Engagements", "/Projects", "/Tasks?scope=all", "/Finance", "/Reports", "/Settings", "/Users", "/Search?q=test"):
        assert client.get(path).status_code == 200, path
    assert "Create a project first" in client.get("/Tasks/New", headers={"HX-Request": "true"}).text
    assert "Add a client first" in client.get("/Engagements/New", headers={"HX-Request": "true"}).text
    form = client.get("/Clients/New", headers={"HX-Request": "true"})
    invalid = client.post("/Clients", data={"csrf_token": csrf_from(form), "name": "x"}, headers={"HX-Request": "true"})
    assert invalid.status_code == 422
    assert 'hx-target="#modal-root"' in invalid.text and "Please correct the form" in invalid.text

    page = client.get("/Settings")
    saved = client.post("/Settings", data={"csrf_token": csrf_from(page), "business_name": "Northstar Works", "legal_name": "Northstar Works Private Limited", "business_email": "billing@example.com", "business_phone": "+91 99999 99999", "address_line1": "12 Market Road", "city": "Pune", "region": "Maharashtra", "postal_code": "411001", "country": "India", "timezone": "Asia/Kolkata", "currency": "INR", "invoice_prefix": "NW-", "payment_terms_days": "30", "tax_information": "GSTIN TEST123", "invoice_footer": "Payment is appreciated."}, follow_redirects=False)
    assert saved.status_code == 303
    settings = client.get("/Settings")
    assert "Northstar Works" in settings.text and "Asia/Kolkata" in settings.text
