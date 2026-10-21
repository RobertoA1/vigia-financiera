from functools import lru_cache
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore", case_sensitive=False)

    app_name: str = "Vigía Financiera"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://vigia:vigia@db:5432/vigia"
    jwt_secret: str = ""
    field_encryption_key: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    extension_origin: str = ""
    public_app_url: str = "http://localhost:5173"
    require_mfa_roles: str = "admin,analyst"
    mfa_issuer: str = "Vigía Financiera"
    login_limit: int = Field(default=10, ge=1, le=1000)
    login_window_seconds: int = Field(default=900, ge=10, le=86400)
    evaluation_daily_limit: int = Field(default=100, ge=1, le=10000)
    max_request_bytes: int = Field(default=131072, ge=4096, le=1048576)
    retention_days: int = 90
    worker_poll_seconds: float = Field(default=2.0, ge=0.1, le=60)
    job_max_attempts: int = Field(default=4, ge=1, le=10)
    job_lease_seconds: int = Field(default=300, ge=30, le=3600)
    max_report_rows: int = Field(default=10000, ge=1, le=100000)
    report_max_bytes: int = Field(default=20000000, ge=10000, le=100000000)
    smtp_host: str = "mailpit"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "Vigía Financiera <noreply@vigia.local>"
    smtp_starttls: bool = False
    smtp_ssl: bool = False
    smtp_timeout_seconds: int = Field(default=15, ge=1, le=120)
    email_notifications_enabled: bool = True
    webhook_notifications_enabled: bool = False
    outbound_webhook_url: str = ""
    webhook_shared_key: str = ""
    webhook_timeout_seconds: float = Field(default=10.0, ge=0.1, le=60)
    webhook_allow_internal_http: bool = False
    openai_api_key: str = ""
    openai_model: str = "gpt-6-mini"
    ai_enabled: bool = False
    ai_require_external_consent: bool = True
    ai_timeout_seconds: float = Field(default=20.0, ge=1, le=120)
    ai_max_output_tokens: int = Field(default=400, ge=64, le=2000)
    ai_max_input_chars: int = Field(default=12000, ge=256, le=24000)
    ai_max_calls_per_analysis: int = Field(default=4, ge=1, le=4)
    ai_daily_call_limit: int = Field(default=80, ge=1, le=10000)
    ai_daily_token_limit: int = Field(default=160000, ge=1, le=100000000)
    virustotal_api_key: str = ""
    virustotal_enabled: bool = False
    reputation_cache_seconds: int = Field(default=21600, ge=60, le=604800)
    reputation_timeout_seconds: float = Field(default=5.0, ge=0.1, le=60)
    reputation_min_interval_seconds: float = Field(default=16.0, ge=15, le=3600)
    reputation_daily_limit: int = Field(default=450, ge=1, le=500)
    bank_domains_json: str = '{"BCP":{"domains":["viabcp.com"],"aliases":["bcp","viabcp"]},"Interbank":{"domains":["interbank.pe"],"aliases":["interbank"]},"BBVA":{"domains":["bbva.pe"],"aliases":["bbva"]}}'
    risk_moderate_threshold: int = 25
    risk_high_threshold: int = 50
    risk_critical_threshold: int = 75
    bootstrap_admin_email: str = "admin@example.com"
    bootstrap_admin_password: str = ""
    bootstrap_admin_name: str = "Administrador"

    @field_validator("retention_days")
    @classmethod
    def valid_retention(cls, value):
        if not 1 <= value <= 3650:
            raise ValueError("RETENTION_DAYS debe estar entre 1 y 3650")
        return value

    @model_validator(mode="after")
    def validate_security(self):
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET debe tener al menos 32 caracteres aleatorios")
        from cryptography.fernet import Fernet
        try:
            Fernet(self.field_encryption_key.encode())
        except Exception as exc:
            raise ValueError("FIELD_ENCRYPTION_KEY debe ser una clave Fernet válida") from exc
        if self.cookie_samesite not in {"strict", "lax", "none"}:
            raise ValueError("COOKIE_SAMESITE inválido")
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("COOKIE_SAMESITE=none requiere COOKIE_SECURE=true")
        if self.environment == "production" and not self.cookie_secure:
            raise ValueError("Producción requiere cookies seguras")
        if self.environment == "production":
            if not self.public_app_url.startswith("https://"):
                raise ValueError("PUBLIC_APP_URL debe usar HTTPS en producción")
            if any(not (origin.startswith("https://") or origin.startswith("chrome-extension://")) for origin in self.allowed_origins):
                raise ValueError("CORS_ORIGINS requiere orígenes HTTPS explícitos en producción")
            if self.webhook_notifications_enabled and self.outbound_webhook_url and not self.outbound_webhook_url.startswith("https://"):
                trusted_internal = self.webhook_allow_internal_http and self.outbound_webhook_url == "http://n8n:5678/webhook/vigia-alerts"
                if not trusted_internal:
                    raise ValueError("OUTBOUND_WEBHOOK_URL requiere HTTPS o el destino interno n8n autorizado explícitamente")
        if "*" in self.allowed_origins:
            raise ValueError("CORS_ORIGINS no permite comodines")
        if not self.required_mfa_roles.issubset({"admin", "analyst", "user"}):
            raise ValueError("REQUIRE_MFA_ROLES contiene roles desconocidos")
        if not 0 < self.risk_moderate_threshold < self.risk_high_threshold < self.risk_critical_threshold <= 100:
            raise ValueError("Los umbrales de riesgo deben estar ordenados entre 1 y 100")
        if not 1 <= self.access_token_minutes <= 60 or not 1 <= self.refresh_token_days <= 30:
            raise ValueError("Duración de sesión fuera de límites")
        return self

    @property
    def allowed_origins(self):
        return [x.strip().rstrip("/") for x in (self.cors_origins + "," + self.extension_origin).split(",") if x.strip()]

    @property
    def required_mfa_roles(self):
        return {x.strip() for x in self.require_mfa_roles.split(",") if x.strip()}


@lru_cache
def get_settings():
    return Settings()
