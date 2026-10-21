"""Rebuild the genuine Langflow export with lfx==0.2.2 (Langflow 1.6.x engine)."""
import json
from pathlib import Path

from lfx.components.input_output import ChatInput, ChatOutput
from lfx.graph import Graph
from evidence_stage import VigiaEvidenceStage

folder = Path(__file__).parent
sample = {"domain": "bcp-ejemplo.test", "score": 60, "risk": "high", "indicators": [{"code": "brand", "title": "Marca financiera en dominio no oficial", "weight": 25, "group": "brand"}]}
source = ChatInput().set(input_value=json.dumps(sample, ensure_ascii=False), should_store_message=False)
previous = source.message_response
for role in ["context", "correlation", "explanation", "incident_support"]:
    stage = VigiaEvidenceStage().set(input_value=previous, role=role)
    previous = stage.build_output
sink = ChatOutput().set(input_value=previous, should_store_message=False)
graph = Graph(start=source, end=sink, flow_name="Vigía · Cuatro agentes con presupuesto")
payload = graph.dump(description="Evidencia estructurada → contexto → correlación → explicación → gestión. Llamadas autenticadas al backend y presupuesto PostgreSQL compartido. Sin acceso al destino sospechoso.")
roles = ["context", "correlation", "explanation", "incident_support"]
for item in payload["data"]["nodes"]:
    if item["id"].startswith("ChatInput"):
        column = 0
    elif item["id"].startswith("ChatOutput"):
        column = 5
    else:
        role = item["data"]["node"]["template"]["role"]["value"]
        column = roles.index(role) + 1
        item["data"]["node"]["display_name"] = "Vigía · " + role
    item.update({"type": "genericNode", "position": {"x": column * 400, "y": 100}, "width": 320, "selected": False})
payload.update({"id": "18aac1bb-1cd8-49b5-a06e-8e2520f4c24a", "last_tested_version": "1.6.5", "tags": []})
(folder / 'vigia-evidence-agents.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print('Exportado:', len(graph.vertices), 'nodos,', len(graph.edges), 'conexiones')
