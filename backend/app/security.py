import hashlib
import secrets
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet
from fastapi import HTTPException

from .models import utcnow

hasher = PasswordHasher()
# Unknown addresses follow the same expensive password-verification path. The
# random dummy value is never an account credential and is not persisted.
DUMMY_PASSWORD_HASH = hasher.hash(secrets.token_urlsafe(32))


def password_hash(password):
    validate_password(password)
    return hasher.hash(password)


def validate_password(password):
    if not 12 <= len(password) <= 128:
        raise HTTPException(422, "La contraseña debe tener entre 12 y 128 caracteres")


def password_verify(stored, password):
    try:
        return hasher.verify(stored, password)
    except (VerificationError, InvalidHashError):
        return False


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def encrypt(value, settings):
    return Fernet(settings.field_encryption_key.encode()).encrypt(value.encode()).decode()


def decrypt(value, settings):
    return Fernet(settings.field_encryption_key.encode()).decrypt(value.encode()).decode()


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def token_for(user, session, settings):
    now = utcnow()
    return jwt.encode({"sub": user.id, "sid": session.id, "iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes), "iss": "vigia-financiera", "aud": "vigia-api"}, settings.jwt_secret, algorithm="HS256")


def decode_token(token, settings):
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], issuer="vigia-financiera", audience="vigia-api", options={"require": ["sub", "sid", "iat", "exp"]})
    except jwt.PyJWTError:
        raise HTTPException(401, "Sesión inválida o vencida", headers={"WWW-Authenticate": "Bearer"})


def timezone_name(value):
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError, TypeError):
        raise HTTPException(422, "Zona horaria IANA inválida")
    return value


def verify_mfa(user, code, settings):
    if not code:
        return False
    for hashed in user.recovery_code_hashes:
        if secrets.compare_digest(digest(code), hashed):
            user.recovery_code_hashes = [x for x in user.recovery_code_hashes if x != hashed]
            return True
    if not code.isdecimal() or len(code) != 6:
        return False
    totp = pyotp.TOTP(decrypt(user.mfa_secret_encrypted, settings))
    current = int(utcnow().timestamp() // 30)
    for counter in (current - 1, current, current + 1):
        if counter > user.mfa_last_counter and secrets.compare_digest(totp.at(counter * 30), code):
            user.mfa_last_counter = counter
            return True
    return False
