"""Create private local settings; preserve existing non-empty secrets."""
import base64
import os
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if not target.exists():
    target.write_text((root / ".env.example").read_text())
lines = target.read_text().splitlines()
values = {line.split("=", 1)[0]: line.split("=", 1)[1] for line in lines if "=" in line and not line.startswith("#")}
generate = {
    "POSTGRES_PASSWORD": secrets.token_urlsafe(24), "JWT_SECRET": secrets.token_urlsafe(48),
    "FIELD_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    "BOOTSTRAP_ADMIN_PASSWORD": secrets.token_urlsafe(20), "WEBHOOK_SHARED_KEY": secrets.token_urlsafe(40),
    "N8N_ENCRYPTION_KEY": secrets.token_hex(32), "LANGFLOW_SUPERUSER_PASSWORD": secrets.token_urlsafe(24),
    "LANGFLOW_SECRET_KEY": secrets.token_urlsafe(48),
}
for key, value in generate.items():
    if not values.get(key):
        values[key] = value
if "CAMBIAR" in values.get("DATABASE_URL", ""):
    values["DATABASE_URL"] = f"postgresql+psycopg://{values['POSTGRES_USER']}:{values['POSTGRES_PASSWORD']}@db:5432/{values['POSTGRES_DB']}"
target.write_text("\n".join(line.split("=", 1)[0] + "=" + values[line.split("=", 1)[0]] if "=" in line and not line.startswith("#") else line for line in lines) + "\n")
os.chmod(target, 0o600)
print(".env preparado con permisos 600. Consulta las credenciales localmente en ese archivo.")
