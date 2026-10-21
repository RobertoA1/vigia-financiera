"""Local-only API/worker performance and report verification with disposable users.

Run with DATABASE_URL pointing to a local development PostgreSQL instance.
Creates 20 controlled user sessions, sends real API requests, downloads actual
reports, then removes only its own fixture users/records. No provider consent,
SMTP or Internet requests. Do not run against production.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from pathlib import Path
import secrets
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import httpx
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from app.config import get_settings
from app.db import SessionLocal
from app.models import Job, Report, Session, User, utcnow
from app.security import digest, password_hash, token_for


def main():
    cfg = get_settings()
    base = "http://127.0.0.1:8000/api/v1"
    if cfg.environment != "development" or make_url(cfg.database_url).host not in {"localhost", "127.0.0.1"}:
        raise SystemExit("Solo se permite PostgreSQL local y ENVIRONMENT=development")
    fixture_ids, tokens, report_ids = [], [], []
    reports_only = "--reports-only" in sys.argv
    users = 1 if reports_only else 20
    tag = secrets.token_hex(8)
    durations = []
    password = password_hash(secrets.token_urlsafe(32))
    try:
        with SessionLocal.begin() as db:
            for index in range(users):
                user = User(email=f"load-{tag}-{index}@example.invalid",name=f"Prueba local {index+1}",role="user",password_hash=password,email_notifications=False)
                db.add(user); db.flush()
                session = Session(user_id=user.id,refresh_hash=digest(secrets.token_urlsafe(32)),mfa_complete=False,expires_at=utcnow()+timedelta(minutes=10))
                db.add(session); db.flush()
                fixture_ids.append(user.id)
                tokens.append(token_for(user,session,cfg))
        def request(index):
            with httpx.Client(base_url=base,timeout=30,trust_env=False) as client:
                started = time.perf_counter()
                response = client.post("/evaluations",headers={"Authorization":"Bearer "+tokens[index]},json={"url":f"https://lab-{tag}-{index}.invalid/","source":"api","external_consent":False})
                elapsed = (time.perf_counter()-started)*1000
                assert response.status_code == 201, f"evaluation HTTP {response.status_code}"
                result = response.json()
                assert result["status"] == "inconclusive" and result["engine_version"]
                return elapsed
        with ThreadPoolExecutor(max_workers=users) as pool:
            durations = sorted(pool.map(request,range(users)))
        with httpx.Client(base_url=base,timeout=30,trust_env=False,headers={"Authorization":"Bearer "+tokens[0]}) as client:
            for url in ("https://bcp-verifica-lab.invalid/login", "http://interbank-verifica-lab.invalid/login", "https://bbva-confirma-lab.invalid/verificar"):
                result=client.post("/evaluations",json={"url":url,"source":"api","external_consent":False})
                assert result.status_code==201
            for format in ("pdf","docx","xlsx"):
                response=client.post("/reports",json={"kind":"consolidated","format":format})
                assert response.status_code==201
                report_ids.append(response.json()["id"])
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                response=client.get("/reports")
                assert response.status_code==200
                states={r["id"]:r["status"] for r in response.json()["items"]}
                if all(states.get(id)=="complete" for id in report_ids):break
                assert not any(states.get(id)=="failed" for id in report_ids),"Report generation failed"
                time.sleep(.3)
            else:raise AssertionError("Report worker did not finish")
            for format,id in zip(("pdf","docx","xlsx"),report_ids):
                response=client.get(f"/reports/{id}/download")
                assert response.status_code==200 and len(response.content)>1000
                (ROOT/"docs/evidence"/f"sample-report.{format}").write_bytes(response.content)
        summary={"mode":"real FastAPI + PostgreSQL + worker, local host; no external providers", "concurrent_users":users,"requests":len(durations),"all_http_status":201,"authentication":"ephemeral persisted sessions; interactive login verified separately by browser E2E", "http_latency_ms":{"p50":durations[min(users-1,int(users*.5))],"p95":durations[min(users-1,int(users*.95))],"p99":durations[-1]},"reports_downloaded":["pdf","docx","xlsx"],"report_scope":"own disposable academic fixture","fixtures_deleted":True}
        output = "report-verification.json" if reports_only else "local-performance.json"
        (ROOT/"docs/evidence"/output).write_text(json.dumps(summary,indent=2)+"\n")
        print(json.dumps(summary,indent=2))
    finally:
        with SessionLocal.begin() as db:
            if report_ids:
                db.execute(delete(Job).where(Job.kind=="report",Job.payload["report_id"].as_string().in_(report_ids)))
            if fixture_ids:
                db.execute(delete(User).where(User.id.in_(fixture_ids)))


if __name__ == "__main__":
    main()
