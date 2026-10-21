"""SQLite unit tests; TEST_DATABASE_URL switches all API tests to PostgreSQL.

PostgreSQL runs allocate an isolated schema per test, never delete user schemas.
External providers and mail delivery remain mocked in this suite.
"""
import base64
import os
import uuid

os.environ.update(JWT_SECRET="unit-test-secret-only-longer-than-32-characters", FIELD_ENCRYPTION_KEY=base64.urlsafe_b64encode(b"unit-test-encryption-key-32-byte!!").decode(), DATABASE_URL="sqlite:////tmp/vigia-tests-bootstrap.db", AI_ENABLED="false", VIRUSTOTAL_ENABLED="false", EMAIL_NOTIFICATIONS_ENABLED="false", WEBHOOK_SHARED_KEY="test-webhook-key-only", BOOTSTRAP_ADMIN_PASSWORD="test-administrator-password")
# Exactly 32 raw bytes for Fernet (the explanatory string above is not a secret).
os.environ["FIELD_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(b"01234567890123456789012345678901").decode()

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app import db as db_module
from app import worker
from app.db import Base, create_db_engine, get_db
from app.main import app
from app.models import User
from app.security import password_hash


@pytest.fixture
def database(tmp_path, monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    schema = None
    admin_engine = None
    if url:
        schema = "test_" + uuid.uuid4().hex
        admin_engine = create_engine(url)
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = create_db_engine(f"sqlite:///{tmp_path}/test.db")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db_module, "SessionLocal", factory)
    monkeypatch.setattr(worker, "SessionLocal", factory)
    def dependency():
        with factory() as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise
    app.dependency_overrides[get_db] = dependency
    with factory.begin() as session:
        for email, role in (("admin@example.com", "admin"), ("analyst@example.com", "analyst"), ("user@example.com", "user"), ("other@example.com", "user")):
            session.add(User(email=email, name=role, role=role, password_hash=password_hash("correct-horse-battery")))
    yield factory
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
    if schema:
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


@pytest.fixture
def client(database):
    with TestClient(app) as client:
        yield client


def login_as(client, email="user@example.com", **kwargs):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery", "timezone": "America/Lima", **kwargs})
    assert response.status_code == 200, response.text
    return response.json(), {"Authorization": "Bearer " + response.json()["access_token"]}


def enroll(client, email="admin@example.com"):
    import pyotp
    result, headers = login_as(client, email)
    setup = client.post("/api/v1/auth/mfa/setup", headers=headers)
    assert setup.status_code == 200, setup.text
    code = pyotp.TOTP(setup.json()["secret"]).now()
    confirmation = client.post("/api/v1/auth/mfa/confirm", json={"code": code}, headers=headers)
    assert confirmation.status_code == 200, confirmation.text
    return headers, setup.json()["secret"], confirmation.json()["recovery_codes"]
