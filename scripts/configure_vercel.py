"""Generate same-origin Vercel routes using an explicitly configured HTTPS API."""
import json
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
values = dotenv_values(root / ".env")
origin = (values.get("DEPLOYMENT_API_ORIGIN") or "").rstrip("/")
if origin:
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise SystemExit("DEPLOYMENT_API_ORIGIN debe ser un origen HTTPS sin rutas ni credenciales.")
headers = [{"source": "/(.*)", "headers": [
    {"key": "X-Content-Type-Options", "value": "nosniff"},
    {"key": "Referrer-Policy", "value": "same-origin"},
    {"key": "X-Frame-Options", "value": "DENY"},
    {"key": "Permissions-Policy", "value": "camera=(), microphone=(), geolocation=()"},
    {"key": "Content-Security-Policy", "value": "default-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"},
]}]
config = {"$schema": "https://openapi.vercel.sh/vercel.json", "framework": "vite", "buildCommand": "npm --prefix frontend run build", "installCommand": "npm --prefix frontend ci", "outputDirectory": "frontend/dist", "headers": headers}
config["rewrites"] = ([{"source": "/api/:path*", "destination": origin + "/api/:path*"}] if origin else []) + [{"source": "/((?!api/).*)", "destination": "/index.html"}]
(root / "vercel.json").write_text(json.dumps(config, indent=2)+"\n")
print("vercel.json generado. " + ("Proxy HTTPS configurado." if origin else "Frontend preparado; configura DEPLOYMENT_API_ORIGIN antes de desplegar el sistema conectado."))
