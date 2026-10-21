# Evidencia de verificación de automatizaciones

Fecha de ejecución: 21/10/2026. Entorno local de desarrollo; se entregó un correo exclusivamente a Mailpit local. No se enviaron correos por Internet ni se consumió OpenAI.

## n8n 2.44.4

Comando reproducible: `N8N_BIN=/ruta/a/n8n python automations/n8n/verify_flows.py`.

Se ejecutaron la CLI y el servidor n8n reales con base SQLite temporal. Se importaron 2 credenciales desde variables efímeras y 4 workflows, y se publicaron los 4 con el modo de compatibilidad CLI `N8N_USE_WORKFLOW_PUBLICATION_SERVICE=false`. La prueba esperó al registro efectivo de los webhooks: `/healthz` puede responder antes de que todos los flujos estén listos.

Resultados observados:

```json
{
  "n8n_version": "2.44.4",
  "workflows_imported": 4,
  "workflows_published": 4,
  "authenticated_requests": 10,
  "notification_callbacks": 2,
  "scheduled_summaries": 2,
  "checks": [
    "webhook rejects missing key",
    "A alerts",
    "A triggers B critical escalation",
    "C actual cron triggers report",
    "D authenticated ingress",
    "duplicate event skips notification"
  ],
  "backend": "controlled simulated HTTP",
  "openai_executed": false,
  "emails_sent": 0
}
```

La API receptora fue simulada y controlada; la persistencia PostgreSQL y los efectos reales del backend se verifican en sus pruebas correspondientes. El cron se aceleró a cada 2 segundos durante esta prueba. No se ha validado SMTP Gmail con una cuenta real. El JSON exportado incluye `webhookId` estable en cada disparador, necesario para que n8n registre las rutas.

## Langflow / LFX 0.2.2

Comando: `python automations/langflow/verify_flow.py` después de instalar `lfx==0.2.2`.

Salida observada:

```text
PASS: export imported by real LFX, 6 nodes, 5 edges, all 4 stages executed against controlled backend. OpenAI NOT executed.
```

Se importó el JSON mediante `Graph.from_payload` y se ejecutó mediante `Graph.arun`. El receptor HTTP controlado comprobó la cabecera y el orden contexto → correlación → explicación → gestión; devolvió `unavailable` explícito. La visualización completa en la imagen Docker Langflow 1.6.5 requiere la prueba de humo del contenedor del usuario.

## LangChain / API de inteligencia

Nueve pruebas `backend/tests/test_intelligence.py` verifican desactivación, falta de clave, reserva obligatoria de presupuesto, minimización, conteos reputacionales y procedencia, agregados históricos, cuatro agentes LCEL con modelo simulado, rechazo de códigos inventados, timeout, ausencia de filtración de errores y autenticación del puente Langflow. También se construye el adaptador OpenAI real y el esquema estructurado sin invocar la API. Las versiones verificadas son `langchain-core==1.6.12`, `langchain-openai==1.7.2` y `openai==3.36.0`.

## Integración con servicios reales locales

También se ejecutaron pruebas adicionales con FastAPI y PostgreSQL reales del entorno académico, sin modificar `.env`:

- `automations/langflow/verify_local_backend.py`: el motor LFX real recorrió las cuatro etapas autenticadas del endpoint `/automation/intelligence` en la API real. Todas devolvieron `unavailable`, `executed=false`, `reason=disabled`; no se invocó OpenAI.
- `automations/n8n/verify_local_services.py`: n8n real ejecutó el flujo A con una evaluación académica de riesgo alto existente, registró el evento en PostgreSQL mediante la API y envió un mensaje por SMTP a Mailpit local. El callback `accepted` quedó persistido en PostgreSQL. La instancia temporal n8n se detuvo y su base temporal se eliminó al terminar.

Salida de la prueba SMTP real local:

```json
{
  "n8n": "2.44.4 real",
  "backend": "FastAPI real local",
  "persistence": "PostgreSQL real local",
  "smtp": "Mailpit real local 127.0.0.1:1025",
  "recipient": "pruebas@ejemplo.invalid",
  "mailpit_message_id": "1VsA29XfRxQZUc0eOdTyFc",
  "event_id": "local-n8n-24237564-ee63-4074-a9e1-615592fa8d51",
  "callback": "accepted persisted",
  "internet_email_sent": 0,
  "local_messages_delivered": 1
}
```

El mensaje puede revisarse en la bandeja Mailpit de la sesión de desarrollo. Los identificadores corresponden a datos de prueba, no a claves. La prueba local crea marcadores de integración/auditoría y un correo Mailpit; debe ejecutarse solo en un entorno de desarrollo académico con una evaluación de riesgo alto. Para otras conexiones locales admite `LOCAL_DATABASE_URL`, `LOCAL_API_BASE` y `LOCAL_MAILPIT_BASE`; rechaza hosts remotos. El script lee `WEBHOOK_SHARED_KEY` desde `.env` sin imprimirlo y fuerza SMTP a `127.0.0.1:1025`, sin usuario, contraseña ni TLS externo.
