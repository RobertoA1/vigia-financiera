import base64

from pydantic import ValidationError
import pytest

from app.config import Settings


def production(**overrides):
    return Settings(_env_file=None,jwt_secret="test-only-signature-longer-than-32-characters",field_encryption_key=base64.urlsafe_b64encode(b"01234567890123456789012345678901").decode(),environment="production",cookie_secure=True,cors_origins="https://academic.example.com",public_app_url="https://academic.example.com",outbound_webhook_url="http://n8n:5678/webhook/vigia-alerts",**overrides)


def test_disabled_internal_webhook_does_not_prevent_production_startup():
    assert production(webhook_notifications_enabled=False).environment=="production"


def test_production_requires_explicit_opt_in_for_fixed_internal_destination():
    with pytest.raises(ValidationError):
        production(webhook_notifications_enabled=True)
    assert production(webhook_notifications_enabled=True,webhook_allow_internal_http=True).webhook_notifications_enabled


def test_internal_exception_cannot_authorize_arbitrary_http_destination():
    options=dict(_env_file=None,jwt_secret="test-only-signature-longer-than-32-characters",field_encryption_key=base64.urlsafe_b64encode(b"01234567890123456789012345678901").decode(),environment="production",cookie_secure=True,cors_origins="https://academic.example.com",public_app_url="https://academic.example.com",webhook_notifications_enabled=True,webhook_allow_internal_http=True)
    for destination in ("http://169.254.169.254/", "http://n8n:5678/other", "http://attacker.invalid/webhook/vigia-alerts"):
        with pytest.raises(ValidationError):
            Settings(**options,outbound_webhook_url=destination)
