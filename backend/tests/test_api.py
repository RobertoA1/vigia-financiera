import asyncio
import json
from datetime import timedelta

import pyotp
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import Alert, Evaluation, Incident, Job, PrivacyRequest, RecoveryToken, Report, Session, User, utcnow
from app.security import decrypt, digest
from app.worker import purge_expired, run_once
from conftest import enroll, login_as


def test_admin_must_enroll_mfa_and_recovery_codes_are_one_use(client, database):
    response, headers = login_as(client, "admin@example.com")
    assert response["mfa_required"] is True
    assert client.get("/api/v1/users", headers=headers).status_code == 403
    setup = client.post("/api/v1/auth/mfa/setup", headers=headers).json()
    assert client.post("/api/v1/auth/mfa/confirm", headers=headers, json={"code": "000000"}).status_code == 422
    code = pyotp.TOTP(setup["secret"]).now()
    codes = client.post("/api/v1/auth/mfa/confirm", headers=headers, json={"code": code}).json()["recovery_codes"]
    assert len(codes) == 10
    assert client.get("/api/v1/users", headers=headers).status_code == 200
    # The enrollment code cannot be replayed as a new login challenge.
    assert client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "correct-horse-battery", "totp": code}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "correct-horse-battery", "totp": codes[0]}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "correct-horse-battery", "totp": codes[0]}).status_code == 401
    with database() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert setup["secret"] not in user.mfa_secret_encrypted
        assert codes[0] not in json.dumps(user.recovery_code_hashes)


def test_refresh_rotates_and_logout_revokes_access(client):
    response, headers = login_as(client)
    old_cookie = client.cookies.get("vigia_refresh")
    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["user"]["timezone"] == "America/Lima"
    assert client.cookies.get("vigia_refresh") != old_cookie
    assert client.post("/api/v1/auth/refresh", headers={"Origin": "https://evil.invalid"}).status_code == 403
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_role_authorization_and_account_deactivation(client):
    _, user_headers = login_as(client)
    assert client.get("/api/v1/users", headers=user_headers).status_code == 403
    assert client.get("/api/v1/audit", headers=user_headers).status_code == 403
    admin_headers, _, _ = enroll(client)
    created = client.post("/api/v1/users", headers=admin_headers, json={"email": "new@example.com", "name": "Nuevo", "password": "long-password-value", "role": "analyst"})
    assert created.status_code == 201
    assert client.post("/api/v1/users", headers=admin_headers, json={"email": "new@example.com", "name": "Duplicado", "password": "long-password-value"}).status_code == 409
    user_id = client.get("/api/v1/auth/me", headers=user_headers).json()["id"]
    assert client.patch(f"/api/v1/users/{user_id}", headers=admin_headers, json={"active": False}).status_code == 200
    assert client.get("/api/v1/auth/me", headers=user_headers).status_code == 401


def test_evaluation_redaction_rbac_and_incident_deduplication(client, database):
    _, headers = login_as(client)
    url = "http://bcp-seguridad-verificar.example.com/cliente/DNI12345678?token=super-private#secret"
    response = client.post("/api/v1/evaluations", headers=headers, json={"url": url, "external_consent": False})
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["score"] >= 50
    assert item["status"] == "inconclusive" and item["ai"]["reason"] == "consent_required"
    assert "super-private" not in response.text and "DNI12345678" not in response.text
    assert client.get("/api/v1/evaluations", headers=headers).json()["total"] == 1
    assert client.get("/api/v1/alerts", headers=headers).json()["total"] == 1
    assert client.get("/api/v1/incidents", headers=headers).json()["total"] == 1
    _, other_headers = login_as(client, "other@example.com")
    assert client.get(f"/api/v1/evaluations/{item['id']}", headers=other_headers).status_code == 404
    assert client.get("/api/v1/evaluations", headers=other_headers).json()["total"] == 0
    assert client.get("/api/v1/dashboard", headers=other_headers).json()["total_evaluations"] == 0
    admin_headers, _, _ = enroll(client)
    first = client.post("/api/v1/incidents", headers=admin_headers, json={"evaluation_id": item["id"]}).json()
    second = client.post("/api/v1/incidents", headers=admin_headers, json={"evaluation_id": item["id"]}).json()
    assert first["id"] == second["id"]
    assert client.patch(f"/api/v1/incidents/{first['id']}", headers=headers, json={"status": "resolved"}).status_code == 403
    assert client.patch(f"/api/v1/incidents/{first['id']}", headers=admin_headers, json={"status": "resolved", "note": "Verificado"}).json()["status"] == "resolved"
    with database() as db:
        row = db.get(Evaluation, item["id"])
        serialized = json.dumps(row.evidence)
        assert "super-private" not in serialized and "DNI12345678" not in serialized
        assert db.scalar(select(Job).where(Job.kind == "evaluation")) is None


def test_private_urls_and_input_limits(client):
    _, headers = login_as(client)
    for url in ["http://127.0.0.1/admin", "http://192.168.1.1", "javascript:alert(1)", "http://localhost:8000"]:
        assert client.post("/api/v1/evaluations", headers=headers, json={"url": url}).status_code == 422
    assert client.post("/api/v1/evaluations/extract", headers=headers, json={"text": " ".join(f"https://example{i}.com" for i in range(11))}).status_code == 422
    assert client.post("/api/v1/evaluations", headers=headers, content=b"x" * 150000).status_code == 413


def test_extract_does_not_store_text_and_preserves_valid_entries(client):
    _, headers = login_as(client)
    response = client.post("/api/v1/evaluations/extract", headers=headers, json={"text": "Mi DNI es secreto. Revisar https://www.viabcp.com/?otp=000000 y http://127.0.0.1"})
    assert response.status_code == 201, response.text
    assert len(response.json()["evaluations"]) == 1
    assert len(response.json()["rejected"]) == 1
    assert "000000" not in response.text and "Mi DNI" not in response.text


def test_webhook_idempotency_and_shared_key(client, database):
    _, headers = login_as(client)
    evaluation = client.post("/api/v1/evaluations", headers=headers, json={"url": "https://example.com"}).json()
    payload = {"event_id": "evt-stable-123", "type": "incident.escalate", "data": {"evaluation_id": evaluation["id"]}}
    assert client.post("/api/v1/webhooks/events", json=payload).status_code == 401
    key = {"X-Webhook-Key": "test-webhook-key-only"}
    assert client.post("/api/v1/webhooks/events", json=payload, headers=key).json()["duplicate"] is False
    assert client.post("/api/v1/webhooks/events", json=payload, headers=key).json()["duplicate"] is True
    assert client.get("/api/v1/automation/summary", headers=key).json()["open_incidents"] == 1
    callback = {"event_id": "callback1", "status": "delivered", "channel": "email"}
    assert client.post("/api/v1/webhooks/notifications", headers=key, json=callback).json()["duplicate"] is False
    assert client.post("/api/v1/webhooks/notifications", headers=key, json=callback).json()["duplicate"] is True


def test_password_recovery_single_use_and_does_not_disable_mfa(client, database):
    admin_headers, _, _ = enroll(client)
    response = client.post("/api/v1/auth/recovery/request", json={"email": "admin@example.com"})
    unknown = client.post("/api/v1/auth/recovery/request", json={"email": "absent@example.com"})
    assert response.json() == unknown.json()
    with database() as db:
        job = db.scalar(select(Job).where(Job.kind == "email"))
        message = json.loads(decrypt(job.payload["encrypted"], get_settings()))
        token = message["body"].split("?token=", 1)[1].split("\n", 1)[0]
        assert token not in json.dumps(job.payload)
    reset = {"token": token, "password": "updated-long-password"}
    assert client.post("/api/v1/auth/recovery/complete", json=reset).status_code == 200
    assert client.post("/api/v1/auth/recovery/complete", json=reset).status_code == 422
    assert client.get("/api/v1/auth/me", headers=admin_headers).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "updated-long-password"}).status_code == 401


def test_privacy_export_and_encrypted_arco_requests(client, database):
    _, headers = login_as(client)
    response = client.post("/api/v1/privacy/requests", headers=headers, json={"kind": "cancellation", "message": "DNI personal privado"})
    assert response.status_code == 201
    assert "DNI personal" not in response.text
    with database() as db:
        request = db.get(PrivacyRequest, response.json()["id"])
        assert "DNI personal" not in request.message_encrypted
    exported = client.get("/api/v1/privacy/export", headers=headers)
    assert exported.status_code == 200
    assert "password_hash" not in exported.text and "mfa_secret" not in exported.text


def test_report_worker_builds_real_file_and_enforces_ownership(client, database):
    _, headers = login_as(client)
    client.post("/api/v1/evaluations", headers=headers, json={"url": "https://www.viabcp.com"})
    report = client.post("/api/v1/reports", headers=headers, json={"kind": "evaluations", "format": "pdf"})
    assert report.status_code == 201, report.text
    report_id = report.json()["id"]
    assert client.get(f"/api/v1/reports/{report_id}/download", headers=headers).status_code == 409
    assert asyncio.run(run_once()) is True
    download = client.get(f"/api/v1/reports/{report_id}/download", headers=headers)
    assert download.status_code == 200, download.text
    assert download.content.startswith(b"%PDF-")
    _, other_headers = login_as(client, "other@example.com")
    assert client.get(f"/api/v1/reports/{report_id}/download", headers=other_headers).status_code == 404
    assert client.get("/api/v1/reports", headers=other_headers).json()["total"] == 0


def test_worker_fails_durably_after_maximum_attempts(client, database, monkeypatch):
    _, headers = login_as(client)
    report = client.post("/api/v1/reports", headers=headers, json={"kind": "evaluations", "format": "pdf"}).json()
    async def fail(*args):
        raise RuntimeError("sensitive details must never appear in persistent errors")
    monkeypatch.setattr("app.worker.execute_job", fail)
    settings = get_settings().model_copy(update={"job_max_attempts": 1})
    assert asyncio.run(run_once(settings)) is True
    with database() as db:
        row = db.get(Report, report["id"])
        job = db.scalar(select(Job).where(Job.kind == "report"))
        assert row.status == "failed"
        assert job.status == "failed" and job.last_error == "RuntimeError"


def test_retention_purges_evaluation_cascades_alerts_incidents(client, database):
    _, headers = login_as(client)
    item = client.post("/api/v1/evaluations", headers=headers, json={"url": "http://bcp-seguridad-verificar.example.com"}).json()
    with database.begin() as db:
        evaluation = db.get(Evaluation, item["id"])
        evaluation.created_at = utcnow() - timedelta(days=100)
    purge_expired(get_settings())
    with database() as db:
        assert db.get(Evaluation, item["id"]) is None
        assert db.scalar(select(Alert)) is None
        assert db.scalar(select(Incident)) is None


def test_report_organization_scope_is_lost_after_demotion(client, database):
    admin_headers, _, _ = enroll(client)
    report = client.post("/api/v1/reports", headers=admin_headers, json={"kind": "evaluations", "format": "pdf"}).json()
    assert asyncio.run(run_once())
    with database.begin() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        user.role = "user"
    assert client.get(f"/api/v1/reports/{report['id']}/download", headers=admin_headers).status_code == 404


def test_admin_can_process_arco_cancellation_and_revoke_access(client, database):
    _, headers = login_as(client)
    item = client.post("/api/v1/evaluations", headers=headers, json={"url": "https://example.com"}).json()
    request = client.post("/api/v1/privacy/requests", headers=headers, json={"kind": "cancellation", "message": "Solicito cancelación"}).json()
    admin_headers, _, _ = enroll(client)
    action = {"status": "completed", "note": "Identidad verificada y solicitud atendida", "erase_evaluations": True}
    processed = client.patch(f"/api/v1/privacy/requests/{request['id']}", headers=admin_headers, json=action)
    assert processed.status_code == 200, processed.text
    assert processed.json()["status"] == "completed"
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    with database() as db:
        assert db.get(Evaluation, item["id"]) is None
        user = db.get(User, item["user_id"])
        assert not user.active
        assert user.email.endswith("@example.invalid")
        assert user.name == "Cuenta cancelada"


def test_development_only_mfa_reset_revokes_old_sessions(client, database, monkeypatch):
    from app import seed
    from app.config import get_settings
    admin_headers, _, _ = enroll(client)
    monkeypatch.setattr(seed, "SessionLocal", database)
    monkeypatch.setattr(seed, "get_settings", lambda: get_settings().model_copy(update={"environment": "production"}))
    with pytest.raises(SystemExit, match="solo está disponible"):
        seed.reset_mfa("admin@example.com", confirm=True)
    monkeypatch.setattr(seed, "get_settings", get_settings)
    seed.reset_mfa("admin@example.com", confirm=True)
    assert client.get("/api/v1/auth/me", headers=admin_headers).status_code == 401
    result, _ = login_as(client, "admin@example.com")
    assert result["mfa_required"] and not result["user"]["mfa_enabled"]


@pytest.mark.postgres
def test_postgres_runtime_selected(database):
    import os
    if not os.environ.get("TEST_DATABASE_URL"):
        pytest.skip("Configura TEST_DATABASE_URL para verificar PostgreSQL")
    with database() as db:
        assert db.bind.dialect.name == "postgresql"
