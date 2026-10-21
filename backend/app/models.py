import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), default="user")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_mfa_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_mfa_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mfa_last_counter: Mapped[int] = mapped_column(Integer, default=-1)
    recovery_code_hashes: Mapped[list] = mapped_column(JSON, default=list)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    browser_notifications: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (CheckConstraint("role IN ('admin','analyst','user')", name="ck_users_role"), CheckConstraint("mfa_enabled = false OR mfa_secret_encrypted IS NOT NULL", name="ck_users_mfa_secret"))


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    mfa_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecoveryToken(Base):
    __tablename__ = "recovery_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class Evaluation(Base):
    __tablename__ = "evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    domain: Mapped[str] = mapped_column(String(253), index=True)
    url_display: Mapped[str] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer)
    risk: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    source: Mapped[str] = mapped_column(String(24))
    external_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="ck_evaluations_score"),
        CheckConstraint("risk IN ('low','moderate','high','critical')", name="ck_evaluations_risk"),
        CheckConstraint("status IN ('preliminary','complete','pending','inconclusive')", name="ck_evaluations_status"),
        CheckConstraint("source IN ('manual','extension','email','sms','api')", name="ck_evaluations_source"),
    )


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    risk: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (CheckConstraint("risk IN ('low','moderate','high','critical')", name="ck_alerts_risk"),)


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"), unique=True)
    title: Mapped[str] = mapped_column(String(240))
    severity: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    timeline: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (CheckConstraint("severity IN ('low','moderate','high','critical')", name="ck_incidents_severity"), CheckConstraint("status IN ('open','investigating','resolved','dismissed')", name="ck_incidents_status"))


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    format: Mapped[str] = mapped_column(String(8))
    scope: Mapped[str] = mapped_column(String(16), default="own", server_default="own")
    status: Mapped[str] = mapped_column(String(24), default="pending")
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    # Bytes are stored durably in the database; never on an exposed static path.
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        CheckConstraint("kind IN ('evaluations','alerts','incidents','consolidated')", name="ck_reports_kind"),
        CheckConstraint("format IN ('pdf','docx','xlsx')", name="ck_reports_format"),
        CheckConstraint("status IN ('pending','complete','failed')", name="ck_reports_status"),
        CheckConstraint("scope IN ('own','organization')", name="ck_reports_scope"),
    )


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (CheckConstraint("kind IN ('evaluation','report','email','webhook')", name="ck_jobs_kind"), CheckConstraint("status IN ('pending','running','complete','failed')", name="ck_jobs_status"), CheckConstraint("attempts >= 0", name="ck_jobs_attempts"))


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    retention_days: Mapped[int] = mapped_column(Integer, default=90)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    webhook_notifications: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (CheckConstraint("retention_days >= 1 AND retention_days <= 3650", name="ck_policies_retention"), CheckConstraint("id = 1", name="ck_policies_singleton"))


class PrivacyRequest(Base):
    __tablename__ = "privacy_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    message_encrypted: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (CheckConstraint("kind IN ('access','rectification','cancellation','opposition')", name="ck_privacy_kind"), CheckConstraint("status IN ('pending','processing','completed','rejected')", name="ck_privacy_status"))


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(40))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("event_id", "kind"),)


class RateLimit(Base):
    __tablename__ = "rate_limits"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("count >= 0", name="ck_rate_limits_count"),)


class ReputationCache(Base):
    __tablename__ = "reputation_cache"
    domain: Mapped[str] = mapped_column(String(253), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProviderBudget(Base):
    __tablename__ = "provider_budgets"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    next_allowed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint("calls >= 0 AND tokens >= 0", name="ck_provider_budgets_counts"),)
