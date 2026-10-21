"""Database backed provider budgets and cache shared by workers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def cached_reputation(domain: str) -> dict | None:
    from app.db import SessionLocal
    from app.models import ReputationCache
    with SessionLocal() as db:
        row = db.get(ReputationCache, domain)
        if row:
            expires = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None else row.expires_at
            if expires > datetime.now(timezone.utc):
                return dict(row.payload)
    return None


def store_reputation(domain: str, payload: dict, ttl_seconds: int) -> None:
    from app.db import SessionLocal
    from app.models import ReputationCache
    with SessionLocal.begin() as db:
        row = db.get(ReputationCache, domain)
        if not row:
            row = ReputationCache(domain=domain)
            db.add(row)
        row.payload = payload
        row.expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)


def reserve_provider(provider: str, daily_limit: int, *, minimum_interval: float = 0,
                     calls: int = 1, tokens: int = 0, token_limit: int = 0) -> bool:
    """Reserve before calling; rollback never refunds consumed external capacity.

    Rows are locked in PostgreSQL; concurrent first-writer insertion is retried.
    One worker is default, database arbitration also supports future workers.
    """
    from app.db import SessionLocal
    from app.models import ProviderBudget
    now = datetime.now(timezone.utc)
    key = f"{provider}:{now.date().isoformat()}"
    for _ in range(3):
        try:
            with SessionLocal.begin() as db:
                row = db.scalar(select(ProviderBudget).where(ProviderBudget.key == key).with_for_update())
                if row is None:
                    row = ProviderBudget(key=key, calls=0, tokens=0)
                    db.add(row)
                    db.flush()
                if row.calls + calls > daily_limit or (token_limit > 0 and row.tokens + tokens > token_limit):
                    return False
                # Waiting for the row lock may cross another caller's timestamp.
                now = datetime.now(timezone.utc)
                next_at = row.next_allowed_at
                if minimum_interval > 0 and next_at and (next_at.replace(tzinfo=timezone.utc) if next_at.tzinfo is None else next_at) > now:
                    return False
                row.calls += calls
                row.tokens += tokens
                row.next_allowed_at = now + timedelta(seconds=minimum_interval) if minimum_interval > 0 else None
            return True
        except IntegrityError:
            continue
    return False
