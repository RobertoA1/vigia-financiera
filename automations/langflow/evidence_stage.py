"""Trusted Langflow component. API destination and key come only from process env."""
import json
import os

import httpx
from lfx.custom import Component
from lfx.io import DropdownInput, MessageTextInput, Output
from lfx.schema.message import Message


class VigiaEvidenceStage(Component):
    display_name = "Vigía · Analista de evidencia"
    description = "Etapa LangChain con presupuesto persistente y sin navegación al destino."
    icon = "ShieldCheck"
    name = "VigiaEvidenceStage"
    inputs = [
        MessageTextInput(name="input_value", display_name="Evidencia JSON / resultado anterior", required=True),
        DropdownInput(name="role", display_name="Agente", options=["context", "correlation", "explanation", "incident_support"], value="context"),
    ]
    outputs = [Output(name="message", display_name="Resultado estructurado", method="build_output")]

    async def build_output(self) -> Message:
        raw = self.input_value.text if hasattr(self.input_value, "text") else str(self.input_value)
        if len(raw.encode()) > 64000:
            raise ValueError("Entrada mayor de 64 KB")
        payload = json.loads(raw)
        evidence = payload.get("evidence", payload)
        previous = payload.get("agents", {})
        base = os.environ.get("LANGFLOW_API_URL", "http://api:8000/api/v1").rstrip("/")
        key = os.environ.get("WEBHOOK_KEY", "")
        if len(key) < 32:
            raise ValueError("Configure WEBHOOK_KEY en el entorno del servidor Langflow")
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.post(base + "/automation/intelligence",
                headers={"X-Webhook-Key": key}, json={"evidence": evidence, "role": self.role, "previous": previous})
            response.raise_for_status()
        result = response.json()
        previous.update(result.get("agents", {}))
        stages = payload.get("stages", {})
        stages[self.role] = {k: result.get(k) for k in ("status", "executed", "calls", "reason", "model")}
        message = Message(text=json.dumps({"evidence": evidence, "agents": previous, "stages": stages}, ensure_ascii=False))
        self.status = result.get("status", "unknown")
        return message
