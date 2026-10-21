import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import Evaluation, Job, ProviderBudget, User, utcnow
from app.schemas import EvaluationCreate
from app.services import create_evaluation
from app.worker import claim_job, reserve_ai_budget, run_once


def test_external_work_requires_explicit_consent_and_enrichment_is_durable(database, monkeypatch):
    settings = get_settings().model_copy(update={"ai_enabled": True, "openai_api_key": "fake-key-no-network", "ai_daily_token_limit": 1000000})
    with database.begin() as db:
        user = db.scalar(select(User).where(User.email == "user@example.com"))
        without = create_evaluation(db, user, EvaluationCreate(url="https://www.viabcp.com", external_consent=False), settings)
        with_consent = create_evaluation(db, user, EvaluationCreate(url="https://www.viabcp.com", external_consent=True), settings)
        evaluation_id = with_consent.id
    with database() as db:
        jobs = db.scalars(select(Job).where(Job.kind == "evaluation")).all()
        assert len(jobs) == 1 and jobs[0].payload["evaluation_id"] == evaluation_id
    observed = {}
    async def fake_enrich(evidence, settings):
        assert evidence["external_consent"] is True
        return {**evidence, "status": "complete", "reputation": {"status": "available", "provider": "fake"}}
    async def fake_ai(evidence, *, settings):
        observed["history"] = evidence["history_summary"]
        assert settings.ai_reserved_calls == 4
        return {"status": "complete", "executed": True, "calls": 4, "agents": {}}
    monkeypatch.setattr("app.detection.enrich", fake_enrich)
    monkeypatch.setattr("app.intelligence.analyze_evidence", fake_ai)
    assert asyncio.run(run_once(settings))
    with database() as db:
        row = db.get(Evaluation, evaluation_id)
        assert row.status == "complete" and row.evidence["ai"]["calls"] == 4
        assert "external_consent" not in row.evidence
        budget = db.scalar(select(ProviderBudget).where(ProviderBudget.key.like("openai:%")))
        assert budget.calls == 4 and budget.tokens > 0
    assert observed["history"] == {"same_domain_24h": 1, "same_domain_high_30d": 0}


def test_worker_can_reclaim_expired_running_job(database):
    settings = get_settings()
    with database.begin() as db:
        row = Job(kind="report", payload={"report_id": "removed"}, status="running", attempts=1, locked_at=utcnow() - timedelta(seconds=settings.job_lease_seconds + 1))
        db.add(row)
        db.flush()
        job_id = row.id
    assert asyncio.run(run_once(settings))
    with database() as db:
        row = db.get(Job, job_id)
        assert row.status == "complete" and row.attempts == 2


def test_exhausted_crash_recovery_does_not_leave_report_pending(database):
    from app.models import Report
    settings = get_settings()
    with database.begin() as db:
        user = db.scalar(select(User).where(User.email == "user@example.com"))
        report = Report(user_id=user.id, kind="evaluations", format="pdf", status="pending")
        db.add(report)
        db.flush()
        report_id = report.id
        db.add(Job(kind="report", payload={"report_id": report_id}, status="running", attempts=settings.job_max_attempts, locked_at=utcnow() - timedelta(seconds=settings.job_lease_seconds + 1)))
    assert claim_job(settings) is None
    with database() as db:
        assert db.get(Report, report_id).status == "failed"


def test_enrichment_updates_existing_alert_and_incident_severity(database, monkeypatch):
    from app.models import Alert, Incident
    settings = get_settings().model_copy(update={"virustotal_enabled": True})
    with database.begin() as db:
        user = db.scalar(select(User).where(User.email == "user@example.com"))
        evaluation = create_evaluation(db, user, EvaluationCreate(url="http://bcp-seguridad-verificar.example.com", external_consent=True), settings)
        evaluation_id = evaluation.id
        assert evaluation.score >= 50
    async def fake_enrich(evidence, settings):
        return {**evidence, "status": "complete", "score": 95, "risk": "critical", "explanation": "Reputación adicional controlada"}
    monkeypatch.setattr("app.detection.enrich", fake_enrich)
    assert asyncio.run(run_once(settings))
    with database() as db:
        alerts = db.scalars(select(Alert).where(Alert.evaluation_id == evaluation_id)).all()
        incidents = db.scalars(select(Incident).where(Incident.evaluation_id == evaluation_id)).all()
        assert len(alerts) == len(incidents) == 1
        assert alerts[0].message == "Reputación adicional controlada" and alerts[0].risk == "critical"
        assert incidents[0].severity == "critical"


@pytest.mark.postgres
def test_postgres_budget_reservation_is_atomic_between_workers(database):
    if not os.environ.get("TEST_DATABASE_URL"):
        pytest.skip("Requiere PostgreSQL real")
    settings = get_settings().model_copy(update={"ai_daily_call_limit": 4, "ai_daily_token_limit": 1000000})
    def reserve(_):
        with database() as db:
            return reserve_ai_budget(db, settings, calls=1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(8)))
    assert sum(results) == 4
    with database() as db:
        row = db.scalar(select(ProviderBudget))
        assert row.calls == 4


@pytest.mark.postgres
def test_postgres_workers_claim_distinct_jobs_skip_locked(database):
    if not os.environ.get("TEST_DATABASE_URL"):
        pytest.skip("Requiere PostgreSQL real")
    with database.begin() as db:
        db.add_all([Job(kind="report", payload={"report_id": "one"}), Job(kind="report", payload={"report_id": "two"})])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim_job(get_settings()), range(2)))
    assert len({result["id"] for result in results}) == 2
    assert claim_job(get_settings()) is None


@pytest.mark.postgres
def test_postgres_user_quota_is_atomic_across_api_transactions(database):
    from fastapi import HTTPException
    from threading import Barrier
    if not os.environ.get("TEST_DATABASE_URL"):
        pytest.skip("Requiere PostgreSQL real")
    settings = get_settings().model_copy(update={"evaluation_daily_limit": 1})
    barrier = Barrier(2)
    def submit(_):
        try:
            with database.begin() as db:
                user = db.scalar(select(User).where(User.email == "user@example.com"))
                barrier.wait(timeout=5)
                create_evaluation(db, user, EvaluationCreate(url="https://www.viabcp.com"), settings)
            return 201
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(submit, range(2)))
    assert sorted(statuses) == [201, 429]
