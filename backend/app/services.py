import re
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select

from .models import Alert, Audit, Evaluation, Incident, Job, Policy, RateLimit, Report, User, utcnow
from .security import aware, digest, encrypt


def user_dict(user):
    return {key: getattr(user, key) for key in ("id", "email", "name", "role", "active", "mfa_enabled", "timezone", "email_notifications", "browser_notifications")}


def evaluation_dict(row):
    data = dict(row.evidence)
    data.update({key: getattr(row, key) for key in ("id", "user_id", "domain", "url_display", "score", "risk", "status", "source", "created_at", "updated_at")})
    for key, default in {"indicators": [], "sources": [], "explanation": "", "recommendations": [], "engine_version": "1.0.0", "ai": None, "reputation": None, "latency_ms": 0}.items():
        data.setdefault(key, default)
    # Internal flags are deliberately excluded from the API.
    return {key: data[key] for key in ("id", "user_id", "domain", "url_display", "score", "risk", "status", "source", "created_at", "updated_at", "indicators", "sources", "explanation", "recommendations", "engine_version", "ai", "reputation", "latency_ms")}


def row_dict(row, exclude=()):
    return {col.name: getattr(row, col.name) for col in row.__table__.columns if col.name not in exclude}


def audit(db, actor, action, target=None, detail=None):
    db.add(Audit(actor_id=actor.id if actor else None, action=action, target_id=target, detail=detail or {}))


def get_policy(db, settings):
    policy = db.get(Policy, 1)
    if not policy:
        policy = Policy(id=1, retention_days=settings.retention_days, email_notifications=settings.email_notifications_enabled, webhook_notifications=settings.webhook_notifications_enabled)
        db.add(policy)
        db.flush()
    return policy


def scoped(statement, user, owner=Evaluation.user_id):
    return statement.where(owner == user.id) if user.role == "user" else statement


def evaluation_access(db, evaluation_id, user):
    row = db.scalar(scoped(select(Evaluation).where(Evaluation.id == evaluation_id), user))
    if not row:
        raise HTTPException(404, "Evaluación no encontrada")
    return row


def limit_request(db, key, maximum, seconds):
    now = utcnow()
    identity = digest(key)
    if db.bind.dialect.name == "postgresql":
        # Cross-process atomic increment; avoids races between API replicas.
        from sqlalchemy.dialects.postgresql import insert
        stmt = insert(RateLimit).values(key=identity, count=1, reset_at=now + timedelta(seconds=seconds))
        stmt = stmt.on_conflict_do_update(index_elements=[RateLimit.key], set_={"count": func.coalesce(RateLimit.count, 0) + 1})
        db.execute(stmt)
    else:
        row = db.get(RateLimit, identity)
        if not row:
            db.add(RateLimit(key=identity, count=1, reset_at=now + timedelta(seconds=seconds)))
            db.flush()
        else:
            row.count += 1
    row = db.scalar(select(RateLimit).where(RateLimit.key == identity).with_for_update())
    if aware(row.reset_at) <= now:
        row.count = 1
        row.reset_at = now + timedelta(seconds=seconds)
    exceeded = row.count > maximum
    db.commit()  # Failed attempts must survive the request rollback.
    if exceeded:
        raise HTTPException(429, "Demasiados intentos; inténtalo más tarde", headers={"Retry-After": str(seconds)})


def incident_for(db, evaluation, actor=None, title=None):
    # Serialize the idempotency lookup and insert for this evaluation.
    db.scalar(select(Evaluation.id).where(Evaluation.id == evaluation.id).with_for_update())
    existing = db.scalar(select(Incident).where(Incident.evaluation_id == evaluation.id))
    if existing:
        return existing
    incident = Incident(evaluation_id=evaluation.id, title=title or f"Enlace sospechoso: {evaluation.domain}", severity=evaluation.risk, status="open", timeline=[{"at": utcnow().isoformat(), "actor": actor.id if actor else "system", "action": "created", "note": "Incidente registrado"}])
    db.add(incident)
    db.flush()
    return incident


def notify_risk(db, evaluation, settings):
    existing = db.scalar(select(Alert).where(Alert.evaluation_id == evaluation.id))
    if existing:
        existing.risk = evaluation.risk
        existing.message = evaluation.evidence.get("explanation", existing.message)
        incident = db.scalar(select(Incident).where(Incident.evaluation_id == evaluation.id))
        ranks = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
        if incident and ranks.get(evaluation.risk, 0) > ranks.get(incident.severity, 0):
            incident.severity = evaluation.risk
            incident.updated_at = utcnow()
            incident.timeline = incident.timeline + [{"at": incident.updated_at.isoformat(), "actor": "system", "action": "risk_updated", "note": "La evidencia complementaria elevó la severidad"}]
        return
    if evaluation.score < settings.risk_high_threshold:
        return
    alert = Alert(evaluation_id=evaluation.id, user_id=evaluation.user_id, title=f"Riesgo detectado en {evaluation.domain}", risk=evaluation.risk, message=evaluation.evidence.get("explanation", "Revisa el enlace antes de continuar"))
    db.add(alert)
    incident_for(db, evaluation)
    policy = get_policy(db, settings)
    user = db.get(User, evaluation.user_id)
    if settings.email_notifications_enabled and policy.email_notifications and user.email_notifications:
        # Notifications contain only the redacted domain, never a clickable suspicious URL.
        db.add(Job(kind="email", payload={"encrypted": encrypt(__import__("json").dumps({"to": user.email, "subject": "Vigía: alerta de enlace sospechoso", "body": f"Se detectó riesgo {evaluation.risk} en el dominio {evaluation.domain}. Ingresa al panel para revisar los indicadores."}), settings), "evaluation_id": evaluation.id, "user_id": user.id}))
    if settings.webhook_notifications_enabled and policy.webhook_notifications and settings.outbound_webhook_url:
        from .models import uid
        db.add(Job(kind="webhook", payload={"event_id": uid(), "type": "risk.alert", "data": {"evaluation_id": evaluation.id, "risk": evaluation.risk, "score": evaluation.score, "domain": evaluation.domain, "notification_allowed": bool(user.email_notifications)}}))


def create_evaluation(db, user, payload, settings):
    from .detection import evaluate_url
    now = utcnow()
    # Serialize each user's quota check + INSERT across API replicas. Extraction
    # batches retain this lock until their encompassing transaction commits.
    locked_user = db.scalar(select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))
    if not locked_user or not locked_user.active:
        raise HTTPException(401, "La cuenta no está activa")
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    count = db.scalar(select(func.count()).select_from(Evaluation).where(Evaluation.user_id == user.id, Evaluation.created_at >= day_start))
    if count >= settings.evaluation_daily_limit:
        raise HTTPException(429, "Se alcanzó la cuota diaria de evaluaciones")
    try:
        evidence = evaluate_url(payload.url, source=payload.source, settings=settings)
    except ValueError as exc:
        # Invalid input is never reflected in error messages or persisted.
        raise HTTPException(422, "URL inválida, privada o no permitida") from exc
    # A strict allowlist prevents raw URL, original text or arbitrary detection internals
    # from accidentally becoming durable data.
    keys = {"domain", "url_display", "score", "risk", "status", "source", "indicators", "sources", "explanation", "recommendations", "engine_version", "ai", "reputation", "latency_ms"}
    evidence = {key: value for key, value in evidence.items() if key in keys}
    needs_work = payload.external_consent and (settings.virustotal_enabled or settings.ai_enabled)
    evidence["status"] = "preliminary" if needs_work else "inconclusive"
    if not needs_work:
        reason = "consent_required" if not payload.external_consent else "providers_disabled"
        evidence["reputation"] = {"provider": "virustotal", "status": "skipped", "reason": reason}
        evidence["ai"] = {"provider": "openai", "status": "unavailable", "executed": False, "reason": reason, "calls": 0, "agents": {}}
    row = Evaluation(user_id=user.id, domain=evidence["domain"], url_display=evidence["url_display"], score=evidence["score"], risk=evidence["risk"], status=evidence["status"], source=payload.source, external_consent=payload.external_consent, evidence=evidence)
    db.add(row)
    db.flush()
    if needs_work:
        db.add(Job(kind="evaluation", payload={"evaluation_id": row.id}))
    notify_risk(db, row, settings)
    audit(db, user, "evaluation.created", row.id, {"external_consent": payload.external_consent, "source": payload.source})
    return row


def report_dict(row):
    return row_dict(row, exclude=("user_id", "content", "error", "scope"))


def create_report(db, user, payload, settings):
    if payload.date_from and payload.date_to and aware(payload.date_from) > aware(payload.date_to):
        raise HTTPException(422, "El inicio del período debe preceder al final")
    pending = db.scalar(select(func.count()).select_from(Report).where(Report.user_id == user.id, Report.status == "pending"))
    if pending >= 5:
        raise HTTPException(429, "Ya tienes cinco reportes pendientes")
    row = Report(user_id=user.id, kind=payload.kind, format=payload.format, scope="own" if user.role == "user" else "organization", filters=payload.model_dump(mode="json", exclude={"kind", "format"}, exclude_none=True))
    db.add(row)
    db.flush()
    db.add(Job(kind="report", payload={"report_id": row.id}))
    audit(db, user, "report.requested", row.id, {"kind": row.kind, "format": row.format})
    return row
