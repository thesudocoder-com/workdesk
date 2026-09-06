import re

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from litestar.testing import TestClient

from Application.Configurations import PROJECT_DIR
from Application.Main import app
from Application.Users.Repository import SessionFactory


@pytest.fixture()
def database(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("WORKDESK_DATABASE_URL", url)
    config = Config(str(PROJECT_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    test_engine = create_engine(url, connect_args={"check_same_thread": False})
    original_bind = SessionFactory.kw.get("bind")
    SessionFactory.configure(bind=test_engine)
    yield url
    SessionFactory.configure(bind=original_bind)
    test_engine.dispose()


@pytest.fixture()
def client(database):
    with TestClient(app=app) as test_client:
        yield test_client


def csrf_from(response) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match, response.text[:500]
    return match.group(1)


def setup_owner(client, *, email="owner@example.com", password="secure-owner-password"):
    page = client.get("/Setup")
    response = client.post("/Setup", data={
        "csrf_token": csrf_from(page),
        "setup_token": "development-setup-token",
        "workspace_name": "Test Studio",
        "name": "Workspace Owner",
        "email": email,
        "password": password,
        "password_confirmation": password,
    }, follow_redirects=False)
    assert response.status_code == 303
    return response


def login(client, email, password):
    page = client.get("/Login")
    return client.post("/Login", data={"email": email, "password": password, "csrf_token": csrf_from(page)}, follow_redirects=False)
