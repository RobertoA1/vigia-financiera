"""Durable PostgreSQL queue. Run separately with ``python -m app.worker``.

SKIP LOCKED allows independent workers; external delivery is at least once.
Every network call has a deadline and retries use persistent exponential backoff.
"""
import asyncio
import base64
import json
import logging
import signal
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage

import httpx
from sqlalchemy import and_, delete, func, or_, select

from .config import get_settings
from .db import SessionLocal
from .models import Alert, Audit, Evaluation, Incident, Job, Policy, PrivacyRequest, RateLimit, RecoveryToken, Report, ReputationCache, Session, User, utcnow
from .security import aware, decrypt
from .services import audit, evaluation_dict, get_policy, notify_risk, row_dict, scoped

logger = logging.getLogger("vigia.worker")


def reserve_ai_budget(db, settings, calls=4):
    from .provider_state import reserve_provider
    # Conservative bound counts every input character as a token, with overhead
    # for the system prompt/schema and all possible output tokens.
    tokens = calls * (settings.ai_max_input_chars + settings.ai_max_output_tokens + 4000)
    return reserve_provider("openai", settings.ai_daily_call_limit, calls=calls, tokens=tokens, token_limit=settings.ai_daily_token_limit)


def claim_job(settings):
    now = utcnow()
    with SessionLocal.begin() as db:
        stmt = select(Job).where(or_(and_(Job.status == "pending", Job.available_at <= now), and_(Job.status == "running", Job.locked_at <= now - timedelta(seconds=settings.job_lease_seconds)))).order_by(Job.available_at, Job.created_at).with_for_update(skip_locked=True).limit(1)
        job = db.scalar(stmt)
        if not job:
            return None
        if job.attempts >= settings.job_max_attempts:
            job.status = "failed"
            job.last_error = "Límite de intentos alcanzado tras reinicio del worker"
            job.completed_at = now
            if job.kind == "report":
                report = db.get(Report, job.payload.get("report_id"))
                if report:
                    report.status, report.error = "failed", "WorkerLeaseExpired"
            elif job.kind == "evaluation":
                evaluation = db.get(Evaluation, job.payload.get("evaluation_id"))
                if evaluation:
                    evaluation.status = "inconclusive"
            audit(db, None, "job.failed", job.id, {"kind": job.kind, "error": "WorkerLeaseExpired"})
            return None
        job.status = "running"
        job.locked_at = now
        job.attempts += 1
        return {"id": job.id, "kind": job.kind, "payload": dict(job.payload), "attempt": job.attempts}


async def process_evaluation(payload, settings):
    from .detection import enrich
    from .intelligence import analyze_evidence
    with SessionLocal() as db:
        row = db.get(Evaluation, payload["evaluation_id"])
        if not row:
            return
        evidence = {**row.evidence, "external_consent": row.external_consent}
        if not row.external_consent:
            # Defense in depth: a forged queue row cannot override consent.
            row.status = "inconclusive"
            db.commit()
            return
    enriched = await enrich(evidence, settings)
    if settings.ai_enabled and settings.openai_api_key:
        with SessionLocal() as db:
            current = db.get(Evaluation, payload["evaluation_id"])
            owner = db.get(User, current.user_id) if current else None
            if not current or not owner or not owner.active:
                return
            history = select(func.count()).select_from(Evaluation).where(Evaluation.domain == current.domain, Evaluation.id != current.id)
            if owner.role == "user":
                history = history.where(Evaluation.user_id == owner.id)
            enriched["history_summary"] = {"same_domain_24h": db.scalar(history.where(Evaluation.created_at >= utcnow() - timedelta(hours=24))), "same_domain_high_30d": db.scalar(history.where(Evaluation.created_at >= utcnow() - timedelta(days=30), Evaluation.risk.in_(["high", "critical"])))}
            reserved = reserve_ai_budget(db, settings, calls=settings.ai_max_calls_per_analysis)
        if reserved:
            configured = settings.model_copy(update={"ai_reserved_calls": settings.ai_max_calls_per_analysis})
            enriched["ai"] = await analyze_evidence(enriched, settings=configured)
        else:
            enriched["ai"] = {"status": "budget_exhausted", "executed": False, "reason": "Se alcanzó el presupuesto diario de llamadas o tokens", "agents": [], "calls": 0}
    else:
        enriched["ai"] = await analyze_evidence(enriched, settings=settings)
    enriched.pop("external_consent", None)
    with SessionLocal.begin() as db:
        row = db.scalar(select(Evaluation).where(Evaluation.id == payload["evaluation_id"]).with_for_update())
        if not row:
            return
        row.evidence = enriched
        row.score, row.risk = enriched["score"], enriched["risk"]
        row.status = enriched.get("status", "inconclusive")
        row.updated_at = utcnow()
        notify_risk(db, row, settings)
        audit(db, None, "evaluation.enriched", row.id, {"status": row.status, "ai_status": (enriched.get("ai") or {}).get("status")})


def build_report_data(db, report, requester, settings):
    filters = report.filters
    kinds = ["evaluations", "alerts", "incidents"] if report.kind == "consolidated" else [report.kind]
    rows = []
    for kind in kinds:
        model = {"evaluations": Evaluation, "alerts": Alert, "incidents": Incident}[kind]
        stmt = select(model)
        if model is not Evaluation:
            stmt = stmt.join(Evaluation, model.evaluation_id == Evaluation.id)
        if report.scope == "own" or requester.role == "user":
            stmt = stmt.where(Evaluation.user_id == requester.id)
        if filters.get("date_from"):
            stmt = stmt.where(model.created_at >= datetime.fromisoformat(filters["date_from"]))
        if filters.get("date_to"):
            stmt = stmt.where(model.created_at <= datetime.fromisoformat(filters["date_to"]))
        if filters.get("risk"):
            stmt = stmt.where(Evaluation.risk == filters["risk"])
        for item in db.scalars(stmt.order_by(model.created_at.desc()).limit(settings.max_report_rows + 1)):
            data = evaluation_dict(item) if model is Evaluation else row_dict(item)
            if model is Alert:
                jobs = db.scalars(select(Job).where(Job.kind.in_(["email", "webhook"]), or_(Job.payload["evaluation_id"].as_string() == item.evaluation_id, Job.payload["data"]["evaluation_id"].as_string() == item.evaluation_id))).all()
                statuses = {job.status for job in jobs}
                data["notification_status"] = "Error de envío" if "failed" in statuses else "Pendiente" if statuses & {"pending", "running"} else "Aceptado por servicio de envío" if statuses else "No solicitada"
            data["record_type"] = kind
            # Convert datetimes to ISO for exports without locale ambiguity.
            for key, value in list(data.items()):
                if isinstance(value, datetime):
                    data[key] = aware(value).isoformat()
            rows.append(data)
            if len(rows) > settings.max_report_rows:
                raise ValueError("Demasiadas filas: reduce el período del reporte")
    return rows


async def process_report(payload, settings):
    from .reporting import render_report
    with SessionLocal() as db:
        report = db.get(Report, payload["report_id"])
        if not report:
            return
        requester = db.get(User, report.user_id)
        if not requester or not requester.active:
            raise ValueError("Solicitante inactivo")
        rows = build_report_data(db, report, requester, settings)
        metadata = {"report_id": report.id, "requester": requester.name, "timezone": requester.timezone or "UTC", "generated_at": utcnow().isoformat(), "filters": report.filters, "scope": "own" if requester.role == "user" else report.scope, "row_count": len(rows), "brand": settings.app_name}
        kind, format = report.kind, report.format
    content = await asyncio.to_thread(render_report, kind, format, rows, metadata)
    if len(content) > settings.report_max_bytes:
        raise ValueError("Reporte demasiado grande")
    with SessionLocal.begin() as db:
        report = db.get(Report, payload["report_id"])
        if report:
            report.content = base64.b64encode(content).decode()
            report.status = "complete"
            report.error = None
            audit(db, None, "report.completed", report.id, {"rows": len(rows)})


def send_email(payload, settings, job_id):
    message_data = json.loads(decrypt(payload["encrypted"], settings))
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = message_data["to"]
    message["Subject"] = message_data["subject"]
    message["Message-ID"] = f"<{job_id}@vigia.local>"
    message.set_content(message_data["body"])
    if not settings.smtp_host:
        raise ValueError("SMTP no configurado")
    client = smtplib.SMTP_SSL if settings.smtp_ssl else smtplib.SMTP
    kwargs = {"timeout": settings.smtp_timeout_seconds}
    if settings.smtp_ssl:
        kwargs["context"] = ssl.create_default_context()
    with client(settings.smtp_host, settings.smtp_port, **kwargs) as smtp:
        if settings.smtp_starttls:
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


async def deliver_webhook(payload, settings):
    if not settings.outbound_webhook_url or not settings.webhook_shared_key:
        raise ValueError("Webhook no configurado")
    async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds, follow_redirects=False) as client:
        response = await client.post(settings.outbound_webhook_url, json=payload, headers={"X-Webhook-Key": settings.webhook_shared_key, "Idempotency-Key": payload["event_id"]})
        response.raise_for_status()


async def execute_job(claim, settings):
    if claim["kind"] == "evaluation":
        await process_evaluation(claim["payload"], settings)
    elif claim["kind"] == "report":
        await process_report(claim["payload"], settings)
    elif claim["kind"] == "email":
        # Preferences can be withdrawn after the alert was queued.
        if claim["payload"].get("evaluation_id"):
            with SessionLocal() as db:
                evaluation = db.get(Evaluation, claim["payload"]["evaluation_id"])
                user = db.get(User, evaluation.user_id) if evaluation else None
                policy = get_policy(db, settings)
                if not evaluation or not user or not user.active or not user.email_notifications or not policy.email_notifications or not settings.email_notifications_enabled:
                    return
        await asyncio.to_thread(send_email, claim["payload"], settings, claim["id"])
    elif claim["kind"] == "webhook":
        outgoing = dict(claim["payload"])
        with SessionLocal() as db:
            policy = get_policy(db, settings)
            if not settings.webhook_notifications_enabled or not policy.webhook_notifications:
                return
            evaluation_id = outgoing.get("data", {}).get("evaluation_id")
            if evaluation_id:
                evaluation = db.get(Evaluation, evaluation_id)
                user = db.get(User, evaluation.user_id) if evaluation else None
                if not evaluation or not user or not user.active:
                    return
                outgoing["data"] = {**outgoing["data"], "notification_allowed": bool(user.email_notifications)}
        await deliver_webhook(outgoing, settings)
    else:
        raise ValueError("Tipo de trabajo desconocido")


async def run_once(settings=None):
    settings = settings or get_settings()
    claim = claim_job(settings)
    if not claim:
        return False
    error = None
    try:
        await asyncio.wait_for(execute_job(claim, settings), timeout=max(10, settings.job_lease_seconds - 10))
    except Exception as exc:
        # Provider exceptions can contain confidential request content. Persist
        # only the class, never str(exc), traceback or provider response bodies.
        error = type(exc).__name__
        logger.warning("job_failed id=%s kind=%s error=%s", claim["id"], claim["kind"], error)
    with SessionLocal.begin() as db:
        job = db.scalar(select(Job).where(Job.id == claim["id"]).with_for_update())
        if not job or job.attempts != claim["attempt"] or job.status != "running":
            return True
        if error:
            job.last_error = error
            if job.attempts >= settings.job_max_attempts:
                job.status = "failed"
                job.completed_at = utcnow()
                if job.kind == "report":
                    report = db.get(Report, job.payload["report_id"])
                    if report:
                        report.status, report.error = "failed", error
                if job.kind == "evaluation":
                    evaluation = db.get(Evaluation, job.payload["evaluation_id"])
                    if evaluation:
                        evaluation.status = "inconclusive"
                audit(db, None, "job.failed", job.id, {"kind": job.kind, "error": error})
            else:
                job.status = "pending"
                job.available_at = utcnow() + timedelta(seconds=min(300, 5 * 2 ** job.attempts))
        else:
            job.status = "complete"
            job.completed_at = utcnow()
            job.last_error = None
    return True


def purge_expired(settings):
    now = utcnow()
    with SessionLocal.begin() as db:
        policy = get_policy(db, settings)
        cutoff = now - timedelta(days=policy.retention_days)
        expired_owner_ids = db.scalars(select(Evaluation.user_id).where(Evaluation.created_at < cutoff).distinct()).all()
        if expired_owner_ids:
            db.execute(delete(Report).where(or_(Report.scope == "organization", Report.user_id.in_(expired_owner_ids))))
        db.execute(delete(Evaluation).where(Evaluation.created_at < cutoff))
        db.execute(delete(Report).where(Report.created_at < cutoff))
        db.execute(delete(Job).where(Job.created_at < cutoff, Job.status.in_(["complete", "failed"])))
        db.execute(delete(Audit).where(Audit.created_at < cutoff))
        db.execute(delete(Session).where(Session.expires_at < now))
        db.execute(delete(RecoveryToken).where(RecoveryToken.expires_at < now))
        db.execute(delete(RateLimit).where(RateLimit.reset_at < now))
        db.execute(delete(ReputationCache).where(ReputationCache.expires_at < now))
        db.execute(delete(PrivacyRequest).where(PrivacyRequest.created_at < cutoff, PrivacyRequest.status.in_(["completed", "rejected"])))
        audit(db, None, "retention.purged", detail={"retention_days": policy.retention_days})


async def main():
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    next_purge = utcnow()
    while not stop.is_set():
        try:
            if utcnow() >= next_purge:
                purge_expired(settings)
                next_purge = utcnow() + timedelta(hours=1)
            did_work = await run_once(settings)
        except Exception as exc:
            logger.error("worker_iteration_failed error=%s", type(exc).__name__)
            did_work = False
        if not did_work:
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_seconds)
            except asyncio.TimeoutError:
                pass


if __name__ == "__main__":
    asyncio.run(main())
