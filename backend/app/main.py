import base64
import json
import re
import secrets
from datetime import datetime, timedelta
from typing import Annotated

import pyotp
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from .config import Settings, get_settings
from .db import get_db
from .models import Alert, Audit, Evaluation, Incident, Job, PrivacyRequest, RecoveryToken, Report, Session, User, WebhookEvent, utcnow
from .schemas import AlertPatch, EvaluationCreate, ExtractCreate, IncidentCreate, IncidentPatch, Login, MFACode, NotificationCallback, PasswordChange, PolicyPatch, PrivacyCreate, PrivacyPatch, ProfilePatch, RecoveryComplete, RecoveryRequest, ReportCreate, UserCreate, UserPatch, WebhookCreate
from .security import DUMMY_PASSWORD_HASH, aware, decode_token, decrypt, digest, encrypt, password_hash, password_verify, timezone_name, token_for, verify_mfa
from .services import audit, create_evaluation, create_report, evaluation_access, evaluation_dict, get_policy, incident_for, limit_request, report_dict, row_dict, scoped, user_dict

settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0", docs_url="/api/docs" if settings.environment != "production" else None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Webhook-Key"])
bearer = HTTPBearer(auto_error=False)
Db = Annotated[DBSession, Depends(get_db)]
Cfg = Annotated[Settings, Depends(get_settings)]
PREFIX = "/api/v1"
COOKIE = "vigia_refresh"


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Pydantic's default response includes the rejected input (passwords, URLs).
    return JSONResponse({"detail": [{"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]} for error in exc.errors()]}, status_code=422)


@app.middleware("http")
async def request_security(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH"}:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > settings.max_request_bytes:
                return JSONResponse({"detail": "Solicitud demasiado grande"}, status_code=413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


def current_session(db: Db, cfg: Cfg, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if not credentials:
        raise HTTPException(401, "Autenticación requerida", headers={"WWW-Authenticate": "Bearer"})
    claims = decode_token(credentials.credentials, cfg)
    session = db.get(Session, claims["sid"])
    if not session or session.revoked or aware(session.expires_at) <= utcnow() or session.user_id != claims["sub"]:
        raise HTTPException(401, "Sesión inválida o vencida")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Sesión inválida o vencida")
    return user, session


def current_user(auth=Depends(current_session), cfg: Settings = Depends(get_settings)):
    user, session = auth
    if user.role in cfg.required_mfa_roles and (not user.mfa_enabled or not session.mfa_complete):
        raise HTTPException(403, "Completa la matrícula MFA antes de continuar")
    return user


def analyst(user: User = Depends(current_user)):
    if user.role not in {"admin", "analyst"}:
        raise HTTPException(403, "Se requiere rol de analista")
    return user


def admin(user: User = Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Se requiere rol de administrador")
    return user


def require_webhook_key(cfg: Cfg, x_webhook_key: Annotated[str | None, Header()] = None):
    if not cfg.webhook_shared_key or not x_webhook_key or not secrets.compare_digest(x_webhook_key, cfg.webhook_shared_key):
        raise HTTPException(401, "Credencial de integración inválida")


def cookie_origin(request, cfg):
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in cfg.allowed_origins:
        raise HTTPException(403, "Origen no permitido")


def set_refresh(response, token, cfg):
    response.set_cookie(COOKIE, token, max_age=cfg.refresh_token_days * 86400, httponly=True, secure=cfg.cookie_secure, samesite=cfg.cookie_samesite, path=f"{PREFIX}/auth")


def session_result(user, session, cfg):
    return {"access_token": token_for(user, session, cfg), "token_type": "bearer", "user": user_dict(user), "mfa_required": user.role in cfg.required_mfa_roles and (not user.mfa_enabled or not session.mfa_complete)}


@app.get("/health")
def health(db: Db):
    db.execute(select(1))
    return {"status": "ok", "service": "vigia-api"}


@app.post(PREFIX + "/auth/login")
def login(payload: Login, request: Request, response: Response, db: Db, cfg: Cfg):
    client = request.client.host if request.client else "unknown"
    # Do not trust X-Forwarded-For supplied by arbitrary clients.
    limit_request(db, "login-ip:" + client, cfg.login_limit * 5, cfg.login_window_seconds)
    limit_request(db, "login-email:" + payload.email.lower().strip(), cfg.login_limit, cfg.login_window_seconds)
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip()).with_for_update())
    valid_password = password_verify(user.password_hash if user else DUMMY_PASSWORD_HASH, payload.password)
    if not user or not user.active or not valid_password:
        audit(db, None, "auth.login_failed")
        db.commit()
        raise HTTPException(401, "Credenciales inválidas")
    if user.mfa_enabled and not verify_mfa(user, payload.totp, cfg):
        audit(db, user, "auth.mfa_failed")
        db.commit()
        raise HTTPException(401, "Se requiere un código TOTP o de recuperación válido")
    if payload.timezone and user.timezone is None:
        user.timezone = timezone_name(payload.timezone)
    raw = secrets.token_urlsafe(48)
    session = Session(user_id=user.id, refresh_hash=digest(raw), mfa_complete=user.mfa_enabled or user.role not in cfg.required_mfa_roles, expires_at=utcnow() + timedelta(days=cfg.refresh_token_days))
    db.add(session)
    db.flush()
    audit(db, user, "auth.login", session.id)
    db.commit()
    set_refresh(response, raw, cfg)
    return session_result(user, session, cfg)


@app.post(PREFIX + "/auth/refresh")
def refresh(request: Request, response: Response, db: Db, cfg: Cfg):
    cookie_origin(request, cfg)
    raw = request.cookies.get(COOKIE, "")
    session = db.scalar(select(Session).where(Session.refresh_hash == digest(raw)).with_for_update())
    if not session or session.revoked or aware(session.expires_at) <= utcnow():
        raise HTTPException(401, "Sesión de actualización inválida")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Sesión inválida")
    replacement = secrets.token_urlsafe(48)
    session.refresh_hash = digest(replacement)
    db.commit()
    set_refresh(response, replacement, cfg)
    return session_result(user, session, cfg)


@app.post(PREFIX + "/auth/logout")
def logout(request: Request, response: Response, db: Db, cfg: Cfg, auth=Depends(current_session)):
    cookie_origin(request, cfg)
    user, session = auth
    session.revoked = True
    audit(db, user, "auth.logout", session.id)
    db.commit()
    response.delete_cookie(COOKIE, path=f"{PREFIX}/auth", secure=cfg.cookie_secure, httponly=True, samesite=cfg.cookie_samesite)
    return {"ok": True}


@app.get(PREFIX + "/auth/me")
def me(auth=Depends(current_session)):
    return user_dict(auth[0])


@app.patch(PREFIX + "/auth/me")
def update_me(payload: ProfilePatch, db: Db, auth=Depends(current_session)):
    user = auth[0]
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(user, key, timezone_name(value) if key == "timezone" else value)
    audit(db, user, "user.profile_updated", user.id, {"fields": list(payload.model_fields_set)})
    db.commit()
    return user_dict(user)


@app.post(PREFIX + "/auth/mfa/setup")
def mfa_setup(db: Db, cfg: Cfg, auth=Depends(current_session)):
    user = auth[0]
    if user.mfa_enabled:
        raise HTTPException(409, "MFA ya está habilitado")
    secret = pyotp.random_base32()
    user.pending_mfa_secret_encrypted = encrypt(secret, cfg)
    user.pending_mfa_at = utcnow()
    audit(db, user, "auth.mfa_setup", user.id)
    db.commit()
    return {"secret": secret, "uri": pyotp.TOTP(secret).provisioning_uri(user.email, issuer_name=cfg.mfa_issuer)}


@app.post(PREFIX + "/auth/mfa/confirm")
def mfa_confirm(payload: MFACode, db: Db, cfg: Cfg, auth=Depends(current_session)):
    user, session = auth
    limit_request(db, "mfa-enroll:" + user.id, cfg.login_limit, cfg.login_window_seconds)
    db.refresh(user, with_for_update=True)
    if user.mfa_enabled or not user.pending_mfa_secret_encrypted or not user.pending_mfa_at or aware(user.pending_mfa_at) + timedelta(minutes=10) < utcnow():
        raise HTTPException(409, "Inicia nuevamente la configuración MFA")
    secret = decrypt(user.pending_mfa_secret_encrypted, cfg)
    totp = pyotp.TOTP(secret)
    current_counter = int(utcnow().timestamp() // 30)
    matched_counter = next((counter for counter in (current_counter - 1, current_counter, current_counter + 1) if secrets.compare_digest(totp.at(counter * 30), payload.code)), None)
    if matched_counter is None:
        raise HTTPException(422, "Código TOTP inválido")
    codes = [secrets.token_hex(8) for _ in range(10)]
    user.recovery_code_hashes = [digest(code) for code in codes]
    user.mfa_secret_encrypted = user.pending_mfa_secret_encrypted
    user.pending_mfa_secret_encrypted = None
    user.pending_mfa_at = None
    user.mfa_enabled = True
    user.mfa_last_counter = matched_counter
    session.mfa_complete = True
    db.execute(update(Session).where(Session.user_id == user.id, Session.id != session.id).values(revoked=True))
    audit(db, user, "auth.mfa_enabled", user.id)
    db.commit()
    return {"recovery_codes": codes}


@app.post(PREFIX + "/auth/password")
def change_password(payload: PasswordChange, db: Db, cfg: Cfg, auth=Depends(current_session)):
    user, session = auth
    limit_request(db, "password:" + user.id, cfg.login_limit, cfg.login_window_seconds)
    if not password_verify(user.password_hash, payload.current_password):
        raise HTTPException(401, "Contraseña actual inválida")
    user.password_hash = password_hash(payload.password)
    db.execute(update(Session).where(Session.user_id == user.id, Session.id != session.id).values(revoked=True))
    audit(db, user, "auth.password_changed", user.id)
    db.commit()
    return {"ok": True}


@app.post(PREFIX + "/auth/recovery/request")
def recovery_request(payload: RecoveryRequest, request: Request, db: Db, cfg: Cfg):
    client = request.client.host if request.client else "unknown"
    limit_request(db, "recovery-ip:" + client, 10, 3600)
    limit_request(db, "recovery-email:" + payload.email.lower().strip(), 3, 3600)
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip(), User.active.is_(True)))
    if user:
        db.execute(update(RecoveryToken).where(RecoveryToken.user_id == user.id).values(used=True))
        token = secrets.token_urlsafe(48)
        db.add(RecoveryToken(user_id=user.id, token_hash=digest(token), expires_at=utcnow() + timedelta(minutes=30)))
        message = {"to": user.email, "subject": "Vigía: recuperar acceso", "body": f"Para cambiar tu contraseña abre {cfg.public_app_url.rstrip('/')}/recuperar?token={token}\nEl enlace caduca en 30 minutos. La autenticación MFA seguirá siendo obligatoria."}
        db.add(Job(kind="email", payload={"encrypted": encrypt(json.dumps(message), cfg), "user_id": user.id}))
        audit(db, user, "auth.recovery_requested")
    db.commit()
    return {"message": "Si la cuenta existe, recibirás instrucciones para recuperar el acceso"}


@app.post(PREFIX + "/auth/recovery/complete")
def recovery_complete(payload: RecoveryComplete, request: Request, db: Db, cfg: Cfg):
    limit_request(db, "recovery-complete:" + (request.client.host if request.client else "unknown"), cfg.login_limit, cfg.login_window_seconds)
    token = db.scalar(select(RecoveryToken).where(RecoveryToken.token_hash == digest(payload.token)).with_for_update())
    if not token or token.used or aware(token.expires_at) <= utcnow():
        raise HTTPException(422, "Enlace de recuperación inválido o vencido")
    user = db.get(User, token.user_id)
    if not user.active:
        raise HTTPException(422, "Enlace de recuperación inválido o vencido")
    user.password_hash = password_hash(payload.password)
    token.used = True
    db.execute(update(Session).where(Session.user_id == user.id).values(revoked=True))
    audit(db, user, "auth.recovery_completed")
    db.commit()
    return {"ok": True}


@app.post(PREFIX + "/evaluations", status_code=201)
def evaluate(payload: EvaluationCreate, db: Db, cfg: Cfg, user: User = Depends(current_user)):
    limit_request(db, "evaluate:" + user.id, 20, 60)
    row = create_evaluation(db, user, payload, cfg)
    db.commit()
    return evaluation_dict(row)


@app.post(PREFIX + "/evaluations/extract", status_code=201)
def extract(payload: ExtractCreate, db: Db, cfg: Cfg, user: User = Depends(current_user)):
    limit_request(db, "extract:" + user.id, 10, 60)
    urls = list(dict.fromkeys(re.findall(r"https?://[^\s<>\"']+", payload.text)))
    if len(urls) > 10:
        raise HTTPException(422, "El texto contiene más de diez URLs")
    rows, rejected = [], []
    for i, url in enumerate(urls):
        url = url.rstrip(".,;!?)\u3002")
        try:
            with db.begin_nested():
                rows.append(create_evaluation(db, user, EvaluationCreate(url=url, source=payload.source, external_consent=payload.external_consent), cfg))
        except HTTPException as exc:
            if exc.status_code == 429:
                raise
            rejected.append(f"Enlace {i + 1}: URL inválida o no permitida")
    db.commit()
    return {"evaluations": [evaluation_dict(row) for row in rows], "rejected": rejected}


@app.get(PREFIX + "/evaluations")
def evaluations(db: Db, q: str = Query(default="", max_length=253), risk: str | None = None, status: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), user: User = Depends(current_user)):
    stmt = scoped(select(Evaluation), user)
    if q:
        stmt = stmt.where(Evaluation.domain.contains(q, autoescape=True))
    if risk:
        stmt = stmt.where(Evaluation.risk == risk)
    if status:
        stmt = stmt.where(Evaluation.status == status)
    count = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Evaluation.created_at.desc()).offset(offset).limit(limit)).all()
    return {"items": [evaluation_dict(row) for row in rows], "total": count}


@app.get(PREFIX + "/evaluations/{evaluation_id}")
def evaluation_detail(evaluation_id: str, db: Db, user: User = Depends(current_user)):
    return evaluation_dict(evaluation_access(db, evaluation_id, user))


@app.post(PREFIX + "/evaluations/{evaluation_id}/reanalyze")
def reanalyze(evaluation_id: str, db: Db, cfg: Cfg, user: User = Depends(current_user)):
    limit_request(db, "reanalyze:" + user.id, 10, 60)
    row = evaluation_access(db, evaluation_id, user)
    db.refresh(row, with_for_update=True)
    if not row.external_consent:
        raise HTTPException(409, "El análisis externo requiere consentimiento al crear la evaluación; envía una nueva evaluación")
    if not cfg.virustotal_enabled and not cfg.ai_enabled:
        raise HTTPException(409, "No hay proveedores externos habilitados")
    pending = db.scalar(select(Job).where(Job.kind == "evaluation", Job.status.in_(["pending", "running"]), Job.payload["evaluation_id"].as_string() == row.id))
    if not pending:
        row.status = "pending"
        row.updated_at = utcnow()
        db.add(Job(kind="evaluation", payload={"evaluation_id": row.id}))
        audit(db, user, "evaluation.reanalysis_requested", row.id)
    db.commit()
    return evaluation_dict(row)


@app.get(PREFIX + "/dashboard")
def dashboard(db: Db, days: int = Query(7, ge=1, le=365), user: User = Depends(current_user)):
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    stmt = scoped(select(Evaluation).where(Evaluation.created_at >= start), user)
    rows = db.scalars(stmt).all()
    incidents_stmt = select(Incident).join(Evaluation, Incident.evaluation_id == Evaluation.id)
    incidents = db.scalars(scoped(incidents_stmt, user).where(Incident.created_at >= start)).all()
    distribution = {"low": 0, "moderate": 0, "high": 0, "critical": 0}
    trend = {(start + timedelta(days=i)).date().isoformat(): {"date": (start + timedelta(days=i)).date().isoformat(), "total": 0, "suspicious": 0} for i in range(days)}
    for row in rows:
        distribution[row.risk] += 1
        bucket = trend.get(aware(row.created_at).date().isoformat())
        if bucket:
            bucket["total"] += 1
            bucket["suspicious"] += int(row.risk in {"high", "critical"})
    recent = sorted(rows, key=lambda row: aware(row.created_at), reverse=True)[:10]
    return {"total_evaluations": len(rows), "suspicious_evaluations": distribution["high"] + distribution["critical"], "open_incidents": sum(x.status in {"open", "investigating"} for x in incidents), "resolved_incidents": sum(x.status == "resolved" for x in incidents), "risk_distribution": distribution, "trend": list(trend.values()), "recent": [evaluation_dict(row) for row in recent], "geography_available": False}


@app.get(PREFIX + "/alerts")
def alerts(db: Db, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), user: User = Depends(current_user)):
    stmt = scoped(select(Alert), user, Alert.user_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    return {"items": [row_dict(row) for row in db.scalars(stmt.order_by(Alert.created_at.desc()).offset(offset).limit(limit))], "total": total}


@app.patch(PREFIX + "/alerts/{alert_id}")
def mark_alert(alert_id: str, payload: AlertPatch, db: Db, user: User = Depends(current_user)):
    row = db.scalar(scoped(select(Alert).where(Alert.id == alert_id), user, Alert.user_id))
    if not row:
        raise HTTPException(404, "Alerta no encontrada")
    row.read = payload.read
    db.commit()
    return row_dict(row)


@app.get(PREFIX + "/incidents")
def incidents(db: Db, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), user: User = Depends(current_user)):
    stmt = scoped(select(Incident).join(Evaluation, Incident.evaluation_id == Evaluation.id), user)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    return {"items": [row_dict(row) for row in db.scalars(stmt.order_by(Incident.created_at.desc()).offset(offset).limit(limit))], "total": total}


@app.post(PREFIX + "/incidents", status_code=201)
def incident_create(payload: IncidentCreate, db: Db, user: User = Depends(analyst)):
    evaluation = evaluation_access(db, payload.evaluation_id, user)
    row = incident_for(db, evaluation, user, payload.title)
    audit(db, user, "incident.created", row.id)
    db.commit()
    return row_dict(row)


@app.patch(PREFIX + "/incidents/{incident_id}")
def incident_update(incident_id: str, payload: IncidentPatch, db: Db, user: User = Depends(analyst)):
    row = db.scalar(select(Incident).where(Incident.id == incident_id).with_for_update())
    if not row:
        raise HTTPException(404, "Incidente no encontrado")
    changes = payload.model_dump(exclude_unset=True)
    if "assigned_to" in changes and changes["assigned_to"]:
        assignee = db.get(User, changes["assigned_to"])
        if not assignee or not assignee.active or assignee.role not in {"admin", "analyst"}:
            raise HTTPException(422, "El responsable debe ser un analista o administrador activo")
    if "status" in changes and changes["status"] is not None:
        row.status = changes["status"]
    if "assigned_to" in changes:
        row.assigned_to = changes["assigned_to"] or None
    row.updated_at = utcnow()
    row.timeline = row.timeline + [{"at": row.updated_at.isoformat(), "actor": user.id, "action": "updated", "note": payload.note or "Estado o responsable actualizado"}]
    audit(db, user, "incident.updated", row.id, {key: value for key, value in changes.items() if key != "note"})
    db.commit()
    return row_dict(row)


@app.get(PREFIX + "/users")
def users(db: Db, user: User = Depends(admin)):
    rows = db.scalars(select(User).order_by(User.created_at)).all()
    return {"items": [user_dict(row) for row in rows], "total": len(rows)}


@app.post(PREFIX + "/users", status_code=201)
def user_create(payload: UserCreate, db: Db, user: User = Depends(admin)):
    row = User(email=str(payload.email).lower(), name=payload.name, role=payload.role, password_hash=password_hash(payload.password))
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "La dirección ya tiene una cuenta")
    audit(db, user, "user.created", row.id, {"role": row.role})
    db.commit()
    return user_dict(row)


@app.patch(PREFIX + "/users/{user_id}")
def user_update(user_id: str, payload: UserPatch, db: Db, user: User = Depends(admin)):
    row = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not row:
        raise HTTPException(404, "Usuario no encontrado")
    changes = payload.model_dump(exclude_none=True)
    if row.id == user.id and (changes.get("active") is False or changes.get("role", "admin") != "admin"):
        raise HTTPException(409, "No puedes desactivar o degradar tu propia cuenta administrativa")
    for key, value in changes.items():
        setattr(row, key, value)
    if "active" in changes or "role" in changes:
        db.execute(update(Session).where(Session.user_id == row.id).values(revoked=True))
    audit(db, user, "user.updated", row.id, changes)
    db.commit()
    return user_dict(row)


@app.get(PREFIX + "/roles")
def roles(user: User = Depends(admin)):
    return {"items": [{"name": "user", "permissions": ["evaluations:own", "reports:own", "privacy:own", "alerts:own"]}, {"name": "analyst", "permissions": ["evaluations:all", "incidents:manage", "reports:all", "alerts:all"]}, {"name": "admin", "permissions": ["users:manage", "policies:manage", "integrations:read", "audit:read", "privacy:manage", "alerts:all", "evaluations:all", "incidents:manage", "reports:all"]}]}


@app.get(PREFIX + "/integrations")
def integrations(cfg: Cfg, user: User = Depends(admin)):
    def status(name, enabled, configured):
        return {"name": name, "enabled": bool(enabled), "configured": bool(configured), "status": "configured" if enabled and configured else "disabled" if not enabled else "missing_configuration"}
    return {"items": [status("OpenAI", cfg.ai_enabled, cfg.openai_api_key), status("VirusTotal", cfg.virustotal_enabled, cfg.virustotal_api_key), status("SMTP / Gmail", cfg.email_notifications_enabled, cfg.smtp_host), status("n8n / webhook", cfg.webhook_notifications_enabled, cfg.outbound_webhook_url and cfg.webhook_shared_key)]}


@app.get(PREFIX + "/policies")
def policies(db: Db, cfg: Cfg, user: User = Depends(admin)):
    policy = get_policy(db, cfg)
    db.commit()
    return row_dict(policy, exclude=("id",))


@app.patch(PREFIX + "/policies")
def policies_update(payload: PolicyPatch, db: Db, cfg: Cfg, user: User = Depends(admin)):
    policy = get_policy(db, cfg)
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(policy, key, value)
    audit(db, user, "policies.updated", detail=changes)
    db.commit()
    return row_dict(policy, exclude=("id",))


@app.get(PREFIX + "/audit")
def audits(db: Db, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), user: User = Depends(admin)):
    return {"items": [row_dict(row) for row in db.scalars(select(Audit).order_by(Audit.created_at.desc()).offset(offset).limit(limit))], "total": db.scalar(select(func.count()).select_from(Audit))}


@app.post(PREFIX + "/reports", status_code=201)
def report_create(payload: ReportCreate, db: Db, cfg: Cfg, user: User = Depends(current_user)):
    limit_request(db, "report:" + user.id, 10, 3600)
    row = create_report(db, user, payload, cfg)
    db.commit()
    return report_dict(row)


@app.get(PREFIX + "/reports")
def reports(db: Db, user: User = Depends(current_user)):
    # A report is always private to its requester, including administrators.
    rows = db.scalars(select(Report).where(Report.user_id == user.id).order_by(Report.created_at.desc()).limit(200)).all()
    return {"items": [report_dict(row) for row in rows], "total": db.scalar(select(func.count()).select_from(Report).where(Report.user_id == user.id))}


@app.get(PREFIX + "/reports/{report_id}/download")
def report_download(report_id: str, db: Db, user: User = Depends(current_user)):
    row = db.scalar(select(Report).where(Report.id == report_id, Report.user_id == user.id))
    if not row:
        raise HTTPException(404, "Reporte no encontrado")
    if row.scope == "organization" and user.role == "user":
        raise HTTPException(404, "Reporte no encontrado")
    if row.status != "complete" or not row.content:
        raise HTTPException(409, "El reporte aún no está disponible" if row.status != "failed" else "El reporte no pudo generarse; solicita uno nuevo")
    types = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    audit(db, user, "report.downloaded", row.id)
    db.commit()
    return Response(base64.b64decode(row.content), media_type=types[row.format], headers={"Content-Disposition": f'attachment; filename="vigia-{row.id}.{row.format}"'})


@app.get(PREFIX + "/privacy/export")
def privacy_export(db: Db, user: User = Depends(current_user)):
    evaluations = db.scalars(select(Evaluation).where(Evaluation.user_id == user.id)).all()
    audit(db, user, "privacy.exported", user.id)
    db.commit()
    return {"exported_at": utcnow(), "user": user_dict(user), "evaluations": [evaluation_dict(row) for row in evaluations], "alerts": [row_dict(row) for row in db.scalars(select(Alert).where(Alert.user_id == user.id))], "requests": [row_dict(row, exclude=("message_encrypted",)) for row in db.scalars(select(PrivacyRequest).where(PrivacyRequest.user_id == user.id))]}


@app.post(PREFIX + "/privacy/requests", status_code=201)
def privacy_request(payload: PrivacyCreate, db: Db, cfg: Cfg, user: User = Depends(current_user)):
    limit_request(db, "arco:" + user.id, 10, 86400)
    row = PrivacyRequest(user_id=user.id, kind=payload.kind, message_encrypted=encrypt(payload.message, cfg))
    db.add(row)
    db.flush()
    audit(db, user, "privacy.requested", row.id, {"kind": payload.kind})
    db.commit()
    return row_dict(row, exclude=("message_encrypted",))


@app.get(PREFIX + "/privacy/requests")
def privacy_requests(db: Db, cfg: Cfg, user: User = Depends(admin)):
    rows = db.scalars(select(PrivacyRequest).order_by(PrivacyRequest.created_at.desc()).limit(200)).all()
    return {"items": [dict(row_dict(row, exclude=("message_encrypted",)), message=decrypt(row.message_encrypted, cfg)) for row in rows], "total": db.scalar(select(func.count()).select_from(PrivacyRequest))}


@app.patch(PREFIX + "/privacy/requests/{request_id}")
def privacy_process(request_id: str, payload: PrivacyPatch, db: Db, cfg: Cfg, user: User = Depends(admin)):
    row = db.scalar(select(PrivacyRequest).where(PrivacyRequest.id == request_id).with_for_update())
    if not row:
        raise HTTPException(404, "Solicitud no encontrada")
    if row.status in {"completed", "rejected"}:
        raise HTTPException(409, "La solicitud ya fue resuelta")
    if payload.erase_evaluations:
        if row.kind != "cancellation" or payload.status != "completed":
            raise HTTPException(422, "La eliminación solo corresponde a una cancelación completada")
        target = db.get(User, row.user_id)
        if target.role == "admin":
            raise HTTPException(409, "Transfiere y desactiva la cuenta administrativa antes de cancelar sus datos")
        # Reports can embed organization records. Erase all generated artifacts
        # when honoring cancellation, preventing stale copies in old reports.
        db.execute(delete(Report).where((Report.scope == "organization") | (Report.user_id == target.id)))
        owned_evaluation_ids = db.scalars(select(Evaluation.id).where(Evaluation.user_id == target.id)).all()
        db.execute(delete(Job).where(Job.payload["user_id"].as_string() == target.id))
        if owned_evaluation_ids:
            db.execute(delete(Job).where((Job.payload["evaluation_id"].as_string().in_(owned_evaluation_ids)) | (Job.payload["data"]["evaluation_id"].as_string().in_(owned_evaluation_ids))))
        db.execute(delete(Evaluation).where(Evaluation.user_id == target.id))
        db.execute(delete(RecoveryToken).where(RecoveryToken.user_id == target.id))
        db.execute(update(Session).where(Session.user_id == target.id).values(revoked=True))
        target.active = False
        target.mfa_secret_encrypted = None
        target.mfa_enabled = False
        target.pending_mfa_secret_encrypted = None
        target.recovery_code_hashes = []
        target.name = "Cuenta cancelada"
        target.email = f"cancelada-{target.id}@example.invalid"
        target.timezone = None
        target.email_notifications = False
        target.browser_notifications = False
        target.password_hash = password_hash(secrets.token_urlsafe(48))
    row.status = payload.status
    # Notes may contain personal data; encrypt them together with the request.
    original = decrypt(row.message_encrypted, cfg)
    row.message_encrypted = encrypt(original + "\nRespuesta administrativa: " + payload.note, cfg)
    audit(db, user, "privacy.processed", row.id, {"status": payload.status, "erased": payload.erase_evaluations})
    db.commit()
    return row_dict(row, exclude=("message_encrypted",))


@app.post(PREFIX + "/webhooks/events", dependencies=[Depends(require_webhook_key)])
def webhook_events(payload: WebhookCreate, db: Db, cfg: Cfg):
    existing = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == payload.event_id, WebhookEvent.kind == payload.type))
    if existing:
        return {"accepted": True, "duplicate": True}
    marker = WebhookEvent(event_id=payload.event_id, kind=payload.type)
    db.add(marker)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"accepted": True, "duplicate": True}
    if payload.type in {"risk.alert", "incident.escalate"}:
        row = db.get(Evaluation, str(payload.data.get("evaluation_id", "")))
        if not row:
            raise HTTPException(404, "Evaluación no encontrada")
        incident = incident_for(db, row)
        if payload.type == "incident.escalate":
            incident.severity = "critical"
            incident.updated_at = utcnow()
            incident.timeline = incident.timeline + [{"at": utcnow().isoformat(), "actor": "automation", "action": "escalated", "note": "Escalamiento solicitado por automatización"}]
        marker.result = {"incident_id": incident.id}
    else:
        service_user = db.scalar(select(User).where(User.active.is_(True), User.role == "admin").order_by(User.created_at))
        if not service_user:
            raise HTTPException(409, "No hay administrador de servicio")
        report_data = {key: value for key, value in payload.data.items() if key in {"kind", "format", "date_from", "date_to", "risk"}}
        try:
            report_payload = ReportCreate(**report_data)
        except Exception:
            raise HTTPException(422, "Parámetros de reporte inválidos")
        report = create_report(db, service_user, report_payload, cfg)
        marker.result = {"report_id": report.id}
    audit(db, None, "webhook.accepted", payload.event_id, {"type": payload.type})
    db.commit()
    return {"accepted": True, "duplicate": False, **marker.result}


@app.post(PREFIX + "/webhooks/notifications", dependencies=[Depends(require_webhook_key)])
def notification_callback(payload: NotificationCallback, db: Db):
    kind = "notification:" + payload.channel
    existing = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == payload.event_id, WebhookEvent.kind == kind))
    if existing:
        return {"accepted": True, "duplicate": True}
    db.add(WebhookEvent(event_id=payload.event_id, kind=kind, result={"status": payload.status}))
    audit(db, None, "notification.callback", payload.event_id, {"channel": payload.channel, "status": payload.status})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"accepted": True, "duplicate": True}
    return {"accepted": True, "duplicate": False}


@app.get(PREFIX + "/automation/summary", dependencies=[Depends(require_webhook_key)])
def automation_summary(db: Db):
    since = utcnow() - timedelta(days=1)
    return {"period_hours": 24, "evaluations": db.scalar(select(func.count()).select_from(Evaluation).where(Evaluation.created_at >= since)), "suspicious": db.scalar(select(func.count()).select_from(Evaluation).where(Evaluation.created_at >= since, Evaluation.risk.in_(["high", "critical"]))), "open_incidents": db.scalar(select(func.count()).select_from(Incident).where(Incident.status.in_(["open", "investigating"]))), "failed_jobs": db.scalar(select(func.count()).select_from(Job).where(Job.status == "failed")), "generated_at": utcnow()}


@app.post(PREFIX + "/automation/reports", dependencies=[Depends(require_webhook_key)], status_code=201)
def automation_report(payload: ReportCreate, db: Db, cfg: Cfg):
    user = db.scalar(select(User).where(User.active.is_(True), User.role == "admin").order_by(User.created_at))
    if not user:
        raise HTTPException(409, "No hay administrador de servicio")
    limit_request(db, "automation-report", 24, 86400)
    row = create_report(db, user, payload, cfg)
    db.commit()
    return report_dict(row)


# The optional Langflow bridge shares the same durable quota and integration key.
try:
    from .automation_intelligence import router as intelligence_router
    app.include_router(intelligence_router)
except ImportError as exc:
    if exc.name != "app.automation_intelligence":
        raise
