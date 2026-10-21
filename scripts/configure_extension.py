"""Generate public extension defaults from root .env without copying any secrets."""
import json
from pathlib import Path

from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
env = dotenv_values(root / ".env")
config = {
    "apiBase": env.get("EXTENSION_API_BASE", "http://localhost:8000/api/v1"),
    "appUrl": env.get("PUBLIC_APP_URL", "http://localhost:8080"),
    "cacheSeconds": int(env.get("EXTENSION_CACHE_SECONDS", "300")),
    "timeoutMs": int(env.get("EXTENSION_TIMEOUT_MS", "8000")),
    "appName": env.get("APP_NAME", "Vigía Financiera"),
}
(root / "extension" / "config.js").write_text("// Generated public defaults. Never add secrets.\nexport const defaults = Object.freeze(" + json.dumps(config, ensure_ascii=False, indent=2) + ");\n")
print("Configuración pública de la extensión actualizada.")
