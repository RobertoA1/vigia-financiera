"""Authenticated Langflow bridge: fixed endpoint, same persistent quota as worker."""
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from .config import get_settings
from .db import get_db
from .intelligence import analyze_role

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])


class EvidenceInput(BaseModel):
    evidence: dict = Field(default_factory=dict)
    role: Literal["context", "correlation", "explanation", "incident_support"]
    previous: dict = Field(default_factory=dict)


@router.post("/intelligence")
async def langflow_stage(body: EvidenceInput, x_webhook_key: str = Header(default=""), db=Depends(get_db), settings=Depends(get_settings)):
    from .main import require_webhook_key
    from .worker import reserve_ai_budget
    require_webhook_key(x_webhook_key=x_webhook_key, cfg=settings)
    if len(str(body.model_dump()).encode()) > 64000:
        raise HTTPException(413, "Evidencia demasiado grande")
    # Disabled runs remain explicit without consuming budget or calling OpenAI.
    if not settings.ai_enabled or not settings.openai_api_key:
        return await analyze_role(body.evidence, role=body.role, previous=body.previous, settings=settings)
    if not reserve_ai_budget(db, settings, calls=1):
        raise HTTPException(429, "Presupuesto diario de IA agotado")
    configured = settings.model_copy(update={"ai_reserved_calls": 1, "ai_max_calls_per_analysis": 1})
    return await analyze_role(body.evidence, role=body.role, previous=body.previous, settings=configured)
