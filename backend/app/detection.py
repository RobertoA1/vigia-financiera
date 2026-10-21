"""Explainable, non-fetching URL risk engine. Never visits the submitted resource."""
from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from urllib.parse import parse_qsl, unquote, urlsplit

import httpx
import idna
import tldextract
from rapidfuzz.fuzz import ratio

ENGINE_VERSION = "vigia-heuristic-1.0.0"
PSL = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True)
DEFAULT_BANKS = {
    "BCP": {"domains": ["viabcp.com"], "aliases": ["bcp", "viabcp"]},
    "Interbank": {"domains": ["interbank.pe"], "aliases": ["interbank"]},
    "BBVA": {"domains": ["bbva.pe"], "aliases": ["bbva"]},
}
PRIVATE_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home", ".arpa")
TEST_SUFFIXES = (".test", ".invalid", ".example")
AUTH_WORDS = re.compile(r"(?:login|signin|verify|verifica|autentica|cuenta|clave|token|banca|bloqueo|actualiza|seguridad|otp)", re.I)
LOOKALIKES = str.maketrans({"а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s", "ν": "v", "α": "a", "ο": "o", "β": "b", "0": "o", "1": "i"})


def _setting(settings: object | None, name: str, default):
    if settings is None:
        return os.environ.get(name.upper(), default)
    return getattr(settings, name.lower(), getattr(settings, name.upper(), default))


def bank_catalog(settings=None) -> dict:
    raw = _setting(settings, "bank_domains_json", "")
    if not raw:
        return DEFAULT_BANKS
    return json.loads(raw) if isinstance(raw, str) else raw


def normalize_url(raw: str) -> dict:
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 4096:
        raise ValueError("Introduce una URL de hasta 4096 caracteres.")
    raw = raw.strip()
    if any(ord(c) < 32 or ord(c) == 127 for c in raw) or "\\" in raw:
        raise ValueError("La URL contiene caracteres de control o separadores ambiguos.")
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
        if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
            raise ValueError("Solo se permiten direcciones HTTP o HTTPS.")
        if parts.username is not None or parts.password is not None:
            raise ValueError("No se admiten credenciales dentro de una URL.")
        host = parts.hostname
        port = parts.port
        if not host or "%" in host or host.endswith(".."):
            raise ValueError("El dominio no es válido.")
        host = host.rstrip(".").lower()
        try:
            ip = ipaddress.ip_address(host)
            if not ip.is_global or ip.is_multicast or ip.is_unspecified or (ip.version == 6 and ip.ipv4_mapped and not ip.ipv4_mapped.is_global):
                raise ValueError("No se permiten direcciones privadas, locales o reservadas.")
            ascii_host = str(ip)
            unicode_host = ascii_host
        except ValueError as exc:
            if re.fullmatch(r"[0-9a-fA-FxX.:]+", host) and (":" in host or re.fullmatch(r"(?:0x[0-9a-fA-F]+|[0-9.]+)", host)):
                raise ValueError("No se permiten direcciones IP ambiguas, privadas o reservadas.") from exc
            if "No se permiten" in str(exc):
                raise
            if host == "localhost" or host.endswith(PRIVATE_SUFFIXES) or "." not in host:
                raise ValueError("No se permiten nombres de redes locales o internas.") from exc
            try:
                ascii_host = idna.encode(host, uts46=True, std3_rules=True).decode("ascii")
                unicode_host = idna.decode(ascii_host)
            except idna.IDNAError as e:
                raise ValueError("El nombre de dominio no es válido.") from e
            if len(ascii_host) > 253:
                raise ValueError("El nombre de dominio es demasiado largo.")
        is_ip = False
        try:
            canonical_ip = ipaddress.ip_address(ascii_host)
            if not canonical_ip.is_global or canonical_ip.is_multicast or canonical_ip.is_unspecified or (canonical_ip.version == 6 and canonical_ip.ipv4_mapped and not canonical_ip.ipv4_mapped.is_global):
                raise ValueError("No se permiten direcciones privadas, locales o reservadas.")
            is_ip = True
        except ValueError:
            if re.fullmatch(r"[0-9.]+|0x[0-9a-fA-F]+", ascii_host) or ":" in ascii_host:
                raise ValueError("No se permiten direcciones IP privadas, ambiguas o reservadas.")
        if ascii_host == "localhost" or ascii_host.endswith(PRIVATE_SUFFIXES):
            raise ValueError("No se permiten nombres de redes locales o internas.")
        authority = f"[{ascii_host}]" if ":" in ascii_host else ascii_host
        if port and port != (443 if parts.scheme == "https" else 80):
            authority += f":{port}"
        # Only origin survives persistence: even path segments can contain PII/tokens.
        display = f"{parts.scheme.lower()}://{authority}/"
        if parts.path and parts.path != "/":
            display += "[ruta omitida]"
        extracted = PSL(ascii_host)
        return {"domain": ascii_host, "unicode_domain": unicode_host,
                "registered_domain": extracted.top_domain_under_public_suffix or ascii_host,
                "subdomain": extracted.subdomain, "suffix": extracted.suffix,
                "is_ip": is_ip, "scheme": parts.scheme.lower(), "port": port,
                "url_display": display, "path": parts.path, "query": parts.query,
                "fragment": parts.fragment, "length": len(raw)}
    except (ValueError, UnicodeError) as exc:
        raise ValueError(str(exc)) from exc


def risk_for_score(score: int, settings=None) -> str:
    if score >= int(_setting(settings, "risk_critical_threshold", 75)):
        return "critical"
    if score >= int(_setting(settings, "risk_high_threshold", 50)):
        return "high"
    if score >= int(_setting(settings, "risk_moderate_threshold", 25)):
        return "moderate"
    return "low"


def evaluate_url(url: str, source: str = "manual", settings=None) -> dict:
    start = time.perf_counter()
    n = normalize_url(url)
    indicators: list[dict] = []

    def add(code, title, detail, weight, group):
        indicators.append(dict(code=code, title=title, detail=detail, weight=weight, group=group))

    domain = n["domain"]
    labels = domain.split(".")
    decoded = n["unicode_domain"]
    canonical = unicodedata.normalize("NFKC", decoded).translate(LOOKALIKES)
    catalog = bank_catalog(settings)
    matched_official = []
    for bank, data in catalog.items():
        legitimate = any(domain == d or domain.endswith("." + d) for d in data["domains"])
        if legitimate:
            matched_official.append(bank)
            continue
        aliases = data.get("aliases", [bank.lower()])
        tokens = re.split(r"[.\-]", canonical)
        exact = any((a in canonical if len(a) > 3 else a in tokens) for a in aliases)
        fuzzy = any(len(a) >= 4 and ratio(a, token) >= 78 and len(token) >= 4 for a in aliases for token in tokens)
        if exact or fuzzy:
            add("brand_impersonation", f"Posible suplantación de {bank}",
                f"El dominio contiene una referencia similar a {bank}, fuera del catálogo de dominios oficiales. Verifica mediante un canal oficial.",
                50 if exact else 40, "identity")
    if decoded != domain:
        add("idn", "Dominio internacionalizado", "Contiene caracteres Unicode o punycode; revisa posibles similitudes visuales. Unicode por sí solo no demuestra fraude.", 10, "structure")
        scripts = {unicodedata.name(c, "").split(" ")[0] for c in decoded if c.isalpha()}
        if len(scripts & {"LATIN", "CYRILLIC", "GREEK"}) > 1:
            add("mixed_scripts", "Alfabetos combinados", "La mezcla de alfabetos puede dificultar reconocer el dominio.", 20, "structure")
    if n["is_ip"]:
        add("ip_host", "Dirección IP sin dominio", "La identidad del sitio no está expresada mediante un nombre de dominio.", 20, "structure")
    if len(domain) > 65 or len(labels) > 5 or any(len(label) > 35 for label in labels):
        add("complex_host", "Dominio complejo", "Longitud o profundidad elevada; interpreta esta señal junto con otras evidencias.", 15, "structure")
    if domain.count("-") >= 3:
        add("many_hyphens", "Nombre segmentado", "El dominio utiliza numerosos guiones.", 10, "structure")
    if n["scheme"] == "http":
        add("no_tls", "Conexión sin HTTPS", "No hay cifrado TLS indicado en la URL. HTTPS tampoco garantiza legitimidad.", 10, "transport")
    if n["port"] not in (None, 80, 443):
        add("unusual_port", "Puerto no habitual", "Puerto distinto de los habituales para navegación web.", 5, "transport")
    context = unquote(n["path"] + "?" + n["query"])[:4096]
    if AUTH_WORDS.search(domain + context) and not matched_official:
        add("financial_lure", "Contexto de acceso o verificación", "Palabras de autenticación o verificación fuera de un dominio financiero reconocido; no implica fraude por sí solo.", 15, "context")
    keys = {key.lower() for key, _ in parse_qsl(n["query"], max_num_fields=100)} if n["query"].count("&") < 100 else set()
    if keys & {"redirect", "redirect_uri", "return", "next", "url", "continue"}:
        add("redirect_parameter", "Parámetro de redirección", "El enlace contiene un parámetro que podría conducir a otro destino. No se siguieron redirecciones.", 10, "context")
    if n["length"] > 500:
        add("long_url", "Enlace muy extenso", "Un enlace extenso puede ocultar su destino o contener datos personales.", 10, "structure")
    # Signals in the same group are correlated; take their maximum, not their sum.
    groups: dict[str, int] = {}
    for indicator in indicators:
        groups[indicator["group"]] = max(groups.get(indicator["group"], 0), indicator["weight"])
    score = min(100, sum(groups.values()))
    risk = risk_for_score(score, settings)
    explanation = ("Se detectaron indicadores que requieren precaución. " + "; ".join(dict.fromkeys(i["title"] for i in indicators)) + ".") if indicators else "No se detectaron indicadores heurísticos relevantes. Esto no acredita que el sitio sea seguro; falta evidencia externa."
    recommendations = ["Verifica el dominio mediante la aplicación o un canal oficial de tu entidad financiera.", "No compartas contraseñas, códigos OTP ni datos de tarjetas a partir de un enlace recibido."]
    if score >= 50:
        recommendations.insert(0, "Evita continuar o introducir datos hasta verificar la legitimidad del sitio.")
    return {"domain": domain, "url_display": n["url_display"], "score": score,
            "risk": risk, "status": "preliminary", "source": source,
            "indicators": indicators, "sources": [{"provider": "heuristic", "version": ENGINE_VERSION, "checked_at": datetime.now(timezone.utc).isoformat()}],
            "explanation": explanation, "recommendations": recommendations,
            "engine_version": ENGINE_VERSION, "ai": None, "reputation": None,
            "latency_ms": round((time.perf_counter() - start) * 1000, 3)}


def _external_domain_allowed(domain: str) -> bool:
    try:
        n = normalize_url("https://" + domain)
        return not n["is_ip"] and bool(n["suffix"]) and not domain.endswith(TEST_SUFFIXES) and domain not in {"example.com", "example.org", "example.net"}
    except ValueError:
        return False


async def fetch_reputation(domain: str, settings, *, transport=None) -> dict:
    """Read existing domain reports only. Never submit URLs or follow redirects."""
    checked_at = datetime.now(timezone.utc).isoformat()
    base = {"provider": "virustotal", "checked_at": checked_at, "scope": "domain", "domain": domain}
    if not _external_domain_allowed(domain):
        return {**base, "status": "skipped", "reason": "Dominio reservado o no apto para envío externo."}
    key = _setting(settings, "virustotal_api_key", "")
    if not key or not _setting(settings, "virustotal_enabled", False):
        return {**base, "status": "unavailable", "reason": "Proveedor no habilitado o sin credencial."}
    timeout = float(_setting(settings, "reputation_timeout_seconds", 5))
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, transport=transport, trust_env=False) as client:
        # DNS is resolved only for this fixed provider, not for attacker-supplied hosts.
        for attempt in range(1):
            try:
                response = await client.get("https://www.virustotal.com/api/v3/domains/" + domain, headers={"x-apikey": key})
                if response.status_code == 429:
                    return {**base, "status": "rate_limited", "reason": "Cuota del proveedor agotada; sin reintento inmediato."}
                if response.status_code == 404:
                    return {**base, "status": "not_found", "reason": "Sin informe previo; no indica legitimidad."}
                if response.status_code in (401, 403):
                    return {**base, "status": "unavailable", "reason": "Credencial o permiso no válido."}
                response.raise_for_status()
                attributes = response.json().get("data", {}).get("attributes", {})
                stats = attributes.get("last_analysis_stats", {})
                if not stats or not all(isinstance(v, int) and v >= 0 for v in stats.values()):
                    return {**base, "status": "inconclusive", "reason": "El proveedor no entregó estadísticas válidas."}
                return {**base, "status": "available", "stats": stats,
                        "evidence_at": attributes.get("last_analysis_date"),
                        "reference": "https://www.virustotal.com/gui/domain/" + domain}
            except (httpx.HTTPError, ValueError, TypeError):
                return {**base, "status": "unavailable", "reason": "Error o timeout del proveedor; análisis local conservado. Reanaliza después del intervalo de cuota."}
    return {**base, "status": "unavailable"}


async def enrich(evidence: dict, settings: object) -> dict:
    """Called by the durable worker; evidence must include external_consent."""
    result = dict(evidence)
    # Reanalysis replaces the previous provider layer instead of accumulating it.
    local = [dict(i) for i in evidence.get("indicators", []) if i.get("group") != "reputation" and i.get("code") != "reputation_detection"]
    groups = {}
    for indicator in local:
        group = indicator.get("group", "structure")
        groups[group] = max(groups.get(group, 0), int(indicator.get("weight", 0)))
    result["indicators"] = local
    result["score"] = min(100, sum(groups.values()))
    result["risk"] = risk_for_score(result["score"], settings)
    result["explanation"] = ("Se detectaron indicadores que requieren precaución. " + "; ".join(dict.fromkeys(i["title"] for i in local)) + ".") if local else "No se detectaron indicadores heurísticos relevantes. Esto no acredita que el sitio sea seguro; falta evidencia externa."
    result["recommendations"] = ["Verifica el dominio mediante la aplicación o un canal oficial de tu entidad financiera.", "No compartas contraseñas, códigos OTP ni datos de tarjetas a partir de un enlace recibido."]
    if result["score"] >= 50:
        result["recommendations"].insert(0, "Evita continuar o introducir datos hasta verificar la legitimidad del sitio.")
    result["sources"] = [s for s in evidence.get("sources", []) if s.get("provider") != "virustotal"]
    if not evidence.get("external_consent", False):
        result.update(status="inconclusive", reputation={"provider": "virustotal", "status": "skipped", "reason": "Sin consentimiento para consultar reputación de dominio."})
        return result
    # Persistent quota/cache helper is kept separate from classification.
    from app.provider_state import cached_reputation, store_reputation, reserve_provider
    domain = evidence["domain"]
    reputation = cached_reputation(domain)
    if reputation:
        reputation = {**reputation, "cached": True}
    elif not _setting(settings, "virustotal_enabled", False) or not _setting(settings, "virustotal_api_key", "") or not _external_domain_allowed(domain):
        reputation = await fetch_reputation(domain, settings)
    elif not reserve_provider("virustotal", int(_setting(settings, "reputation_daily_limit", 450)), minimum_interval=float(_setting(settings, "reputation_min_interval_seconds", 16))):
        reputation = {"provider": "virustotal", "status": "rate_limited", "reason": "Cuota local o intervalo mínimo; análisis local conservado."}
    else:
        reputation = await fetch_reputation(domain, settings)
        if reputation["status"] in {"available", "not_found"}:
            store_reputation(domain, reputation, int(_setting(settings, "reputation_cache_seconds", 21600)))
    result["reputation"] = reputation
    result["sources"] += [reputation]
    if reputation.get("status") == "available":
        stats = reputation.get("stats", {})
        malicious, suspicious = stats.get("malicious", 0), stats.get("suspicious", 0)
        floor = 85 if malicious >= 3 else 60 if malicious >= 1 else 35 if suspicious >= 2 else 0
        result["score"] = max(result["score"], floor)
        result["risk"] = risk_for_score(result["score"], settings)
        if floor:
            result["indicators"] = local + [{"code": "reputation_detection", "title": "Detecciones de reputación", "detail": f"{malicious} motores maliciosos y {suspicious} sospechosos. Son evidencias de dominio, no una verificación inequívoca de esta URL.", "weight": floor, "group": "reputation"}]
            result["explanation"] += f" VirusTotal reporta {malicious} detecciones maliciosas y {suspicious} sospechosas para el dominio."
            if result["score"] >= 50:
                result["recommendations"] = list(dict.fromkeys(["Evita continuar o introducir datos hasta verificar la legitimidad del sitio."] + result.get("recommendations", [])))
        else:
            result["explanation"] += " No aparecen detecciones reputacionales relevantes; la ausencia de detecciones no garantiza seguridad."
        result["status"] = "complete"
    else:
        result["status"] = "inconclusive"
    return result
