"""Create the initial administrator only when explicitly configured."""
import argparse
from sqlalchemy import select, update
from .config import get_settings
from .db import SessionLocal
from .models import Session, User
from .security import password_hash
from .services import audit, get_policy


def seed_admin():
    settings = get_settings()
    with SessionLocal.begin() as db:
        get_policy(db, settings)
        if db.scalar(select(User).where(User.role == "admin")):
            print("Administrador existente; no se modifica su contraseña.")
            return
        if not settings.bootstrap_admin_password:
            raise SystemExit("Configura BOOTSTRAP_ADMIN_PASSWORD (mínimo 12 caracteres) para crear el primer administrador.")
        user = User(email=settings.bootstrap_admin_email.strip().lower(), name=settings.bootstrap_admin_name, role="admin", password_hash=password_hash(settings.bootstrap_admin_password))
        db.add(user)
        db.flush()
        audit(db, None, "user.bootstrap", user.id)
    print("Administrador creado. Completa la matrícula TOTP en el primer acceso.")


def reset_mfa(email, confirm=False):
    settings = get_settings()
    if settings.environment != "development":
        raise SystemExit("reset-mfa solo está disponible con ENVIRONMENT=development")
    if not confirm:
        raise SystemExit("Agrega --confirm para restablecer MFA y revocar todas las sesiones de la cuenta indicada")
    with SessionLocal.begin() as db:
        user = db.scalar(select(User).where(User.email == email.strip().lower()).with_for_update())
        if not user or user.role != "admin":
            raise SystemExit("La cuenta debe existir y tener rol administrativo")
        user.mfa_enabled = False
        user.mfa_secret_encrypted = None
        user.pending_mfa_secret_encrypted = None
        user.pending_mfa_at = None
        user.mfa_last_counter = -1
        user.recovery_code_hashes = []
        db.execute(update(Session).where(Session.user_id == user.id).values(revoked=True))
        audit(db, None, "auth.dev_mfa_reset", user.id)
    print("MFA restablecido y sesiones revocadas. La cuenta deberá matricular TOTP al ingresar.")


def main():
    parser = argparse.ArgumentParser(description="Administración inicial local de Vigía Financiera")
    subparsers = parser.add_subparsers(dest="command")
    reset = subparsers.add_parser("reset-mfa", help="Restablecer MFA administrativo solo en desarrollo")
    reset.add_argument("--email", required=True)
    reset.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if args.command == "reset-mfa":
        reset_mfa(args.email, args.confirm)
    else:
        seed_admin()


if __name__ == "__main__":
    main()
