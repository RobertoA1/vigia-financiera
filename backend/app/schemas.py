from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Role = Literal["admin", "analyst", "user"]
Risk = Literal["low", "moderate", "high", "critical"]
Source = Literal["manual", "extension", "email", "sms", "api"]
ReportKind = Literal["evaluations", "alerts", "incidents", "consolidated"]
ReportFormat = Literal["pdf", "docx", "xlsx"]


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Payload):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)
    totp: str | None = Field(default=None, max_length=64)
    timezone: str | None = Field(default=None, max_length=64)


class ProfilePatch(Payload):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    timezone: str | None = Field(default=None, max_length=64)
    email_notifications: bool | None = None
    browser_notifications: bool | None = None


class UserCreate(Payload):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=128)
    role: Role = "user"


class UserPatch(Payload):
    role: Role | None = None
    active: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)


class MFACode(Payload):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class PasswordChange(Payload):
    current_password: str = Field(max_length=128)
    password: str = Field(min_length=12, max_length=128)


class RecoveryRequest(Payload):
    email: str = Field(max_length=254)


class RecoveryComplete(Payload):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=12, max_length=128)


class EvaluationCreate(Payload):
    url: str = Field(min_length=4, max_length=4096)
    source: Source = "manual"
    external_consent: bool = False


class ExtractCreate(Payload):
    text: str = Field(min_length=1, max_length=50000)
    source: Source = "email"
    external_consent: bool = False


class AlertPatch(Payload):
    read: bool


class IncidentCreate(Payload):
    evaluation_id: str
    title: str | None = Field(default=None, min_length=1, max_length=240)


class IncidentPatch(Payload):
    status: Literal["open", "investigating", "resolved", "dismissed"] | None = None
    assigned_to: str | None = None
    note: str | None = Field(default=None, max_length=2000)


class PolicyPatch(Payload):
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    email_notifications: bool | None = None
    webhook_notifications: bool | None = None


class ReportCreate(Payload):
    kind: ReportKind = "consolidated"
    format: ReportFormat = "pdf"
    date_from: datetime | None = None
    date_to: datetime | None = None
    risk: Risk | None = None


class PrivacyCreate(Payload):
    kind: Literal["access", "rectification", "cancellation", "opposition"]
    message: str = Field(min_length=1, max_length=4000)


class PrivacyPatch(Payload):
    status: Literal["processing", "completed", "rejected"]
    note: str = Field(min_length=1, max_length=1000)
    # Destructive cancellation is an explicit administrator decision, never
    # triggered merely by user-submitted free text.
    erase_evaluations: bool = False


class WebhookCreate(Payload):
    event_id: str = Field(min_length=1, max_length=128)
    type: Literal["risk.alert", "incident.escalate", "report.request"]
    data: dict = Field(default_factory=dict)


class NotificationCallback(Payload):
    event_id: str = Field(min_length=1, max_length=128)
    status: Literal["delivered", "failed", "accepted"]
    channel: Literal["email", "webhook", "browser"]
    detail: str | None = Field(default=None, max_length=500)
