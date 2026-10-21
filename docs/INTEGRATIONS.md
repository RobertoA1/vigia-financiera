# Integraciones y automatización

## OpenAI y LangChain

El backend implementa cuatro analistas LCEL (`ChatPromptTemplate | ChatOpenAI.with_structured_output`) con esquema Pydantic: contexto financiero, correlación de evidencia, explicación y apoyo a incidentes. Son etapas acotadas: no poseen navegador, shell ni herramientas con efectos externos. Solo reciben dominio, puntuación, códigos/títulos/pesos de indicadores y conteos reputacionales y agregados históricos del mismo dominio cuando están disponibles. No reciben URL completa, parámetros, rutas, correo, identificador de usuario ni contenido de formularios. El puente Langflow solo reutiliza códigos y banderas validados de resultados previos recibidos: descarta texto libre y URLs que pudiera introducir el cliente. Las salidas se muestran como asesoría; nunca reducen ni sustituyen el riesgo determinístico.

`AI_ENABLED=false` desactiva llamadas; `OPENAI_API_KEY` vacía también. `OPENAI_MODEL=gpt-6-mini` conserva el modelo solicitado por el usuario, pero su disponibilidad y precio no se han confirmado en el catálogo público consultado. Antes de habilitar IA debe comprobarse el identificador disponible en la cuenta y sustituirlo si corresponde. No hay elección silenciosa de otro modelo. Un modelo inexistente produce `provider_or_schema_error` y conserva la evaluación heurística.

Variables: `AI_TIMEOUT_SECONDS`, `AI_MAX_OUTPUT_TOKENS`, `AI_MAX_INPUT_CHARS`, `AI_MAX_CALLS_PER_ANALYSIS` (máximo 4), `AI_DAILY_CALL_LIMIT`, `AI_DAILY_TOKEN_LIMIT`. El worker reserva llamadas y un límite conservador de tokens atómicamente en PostgreSQL antes de cada análisis. Cada llamada permite como máximo el límite de salida, tiene cero reintentos automáticos y comparte un plazo total. Las reservas fallidas no se liberan automáticamente: evita exceder la cuota ante timeouts ambiguos. El límite de tokens no equivale a dólares; el costo depende del modelo. Configure además límites monetarios en el proyecto del proveedor. LangSmith no se activa.

Los estados `unavailable`, `partial` y `complete`, `executed`, `calls`, `reason` y el modelo permiten distinguir una caída, ausencia de credenciales y un resultado real. Las pruebas de IA usan modelos **simulados**; no acreditan conectividad con OpenAI.

Fuente de implementación: [ChatOpenAI y salidas estructuradas](https://docs.langchain.com/oss/python/integrations/chat/openai).

## Langflow: flujo visual real

`automations/langflow/vigia-evidence-agents.json` es un export generado por `lfx.Graph.dump`, con seis nodos y cinco conexiones: Chat Input → contexto → correlación → explicación → gestión → Chat Output. Cada etapa contiene el componente Python real de `evidence_stage.py`; llama exclusivamente a `POST /api/v1/automation/intelligence` del backend con `X-Webhook-Key`. El endpoint comparte la cuota PostgreSQL del worker. Los secretos no se incrustan en el JSON.

1. Iniciar servicios Docker y el perfil de Langflow. Configurar `LANGFLOW_API_URL=http://api:8000/api/v1` y `WEBHOOK_KEY` con el mismo valor de `WEBHOOK_SHARED_KEY` del backend. `LANGFLOW_API_URL` es un destino administrativo fijo, no se toma del contenido analizado.
2. Abrir Langflow, importar el JSON y comprobar que aparecen las cuatro etapas conectadas. El editor ejecuta Python de los componentes: acceso exclusivo para administradores; no exponerlo públicamente.
3. En Playground introducir evidencia JSON con `domain`, `score`, `risk`, `indicators`; nunca introducir datos personales ni URLs con tokens. Con IA desactivada se recorren las cuatro etapas y se devuelve explícitamente `unavailable`; no se inventa una respuesta.
4. Para reconstruir/verificar el export: instalar `lfx==0.2.2`, ejecutar `python automations/langflow/build_flow.py` y `python automations/langflow/verify_flow.py`. El segundo utiliza el motor LFX real y un backend local **simulado**, valida autenticación y orden de las cuatro etapas; no ejecuta OpenAI. Se verificó efectivamente este recorrido. También se verificó el recorrido contra la API real local con `python automations/langflow/verify_local_backend.py`: cuatro etapas autenticadas respondieron IA desactivada sin llamar OpenAI. La interfaz completa del contenedor Langflow requiere la prueba de humo del entorno Docker.

El perfil utiliza Langflow 1.6.5; LFX 0.2.2 es el motor con el que se construyó y verificó el JSON. No actualizar versiones sin volver a importar/ejecutar el export. Fuentes: [componentes personalizados](https://docs.langflow.org/components-custom-components), [ejecución de flujos con LFX](https://docs.langflow.org/lfx-run).

## n8n: cuatro flujos importables

Versión fijada: n8n 2.44.4. Los JSON no contienen contraseñas y permanecen **inactivos** al importar. El script `automations/n8n/bootstrap.cjs` crea credenciales desde variables de entorno en un archivo temporal 0600, importa credenciales y flujos mediante la CLI oficial, y elimina el archivo. Ejecutar dentro del contenedor, con `automations/n8n` montado en `/flows`:

```bash
docker compose --profile integrations up -d n8n
docker compose exec -T n8n node /flows/bootstrap.cjs
```

En el primer arranque abrir n8n y completar la creación de la cuenta administradora local antes de importar; después ejecutar bootstrap. En el editor revisar credenciales, zona horaria, destinatario y luego publicar/activar los flujos. `WEBHOOK_KEY` de n8n debe coincidir con `WEBHOOK_SHARED_KEY` del backend. El valor debe tener al menos 32 caracteres; no confundirlo con una clave de proveedor. n8n utiliza credencial Header Auth `X-Webhook-Key` en los tres webhooks de entrada. El entorno permite expresiones `$env` únicamente en esta instancia administrada (`N8N_BLOCK_ENV_ACCESS_IN_NODE=false`); no permitir editores no confiables.

| Flujo | Disparador | Resultado |
|---|---|---|
| A, alertas | POST `/webhook/vigia-alerts` | Registra evento idempotente, verifica tipo y consentimiento, correo opcional al destinatario fijo, callback auditado; riesgo crítico activa B automáticamente. |
| B, escalamiento | POST `/webhook/vigia-escalations` | Solicita escalamiento persistente y propone revisión humana; correo opcional, callback. |
| C, reportes | Cron `REPORT_SCHEDULE_CRON` | Obtiene resumen y solicita PDF consolidado mediante evento `report.request` idempotente por minuto UTC; descarga desde Reportes con cuenta autorizada. |
| D, entrada externa | POST `/webhook/vigia-external` | Remite el evento a la API autenticada; valida tipo, datos e idempotencia en PostgreSQL. No acepta URLs de callback. |

Los paths `/webhook-test/` solo funcionan durante la escucha manual en el editor; los paths `/webhook/` requieren flujos activos. Configurar `OUTBOUND_WEBHOOK_URL=http://n8n:5678/webhook/vigia-alerts` para A; B puede invocarse desde una integración autorizada con `type=incident.escalate`. El backend no envía solicitudes a direcciones proporcionadas por eventos. Para probar, usar el identificador de una evaluación existente y `event_id` único; repetirlo no vuelve a mutar el incidente ni crear otro reporte.

`INTERNAL_API_URL=http://api:8000/api/v1`, `N8N_INTERNAL_URL=http://n8n:5678`, `APP_URL`, `ALERT_RECIPIENT`, `SMTP_FROM`, variables SMTP y `REPORT_SCHEDULE_CRON` configuran el entorno. `N8N_EMAIL_ENABLED` controla el permiso de correo de los flujos y es independiente del correo individual del backend. `GENERIC_TIMEZONE` gobierna el cron de la instancia; cambiar y republicar después de modificar programación. La zona horaria de la cuenta web es independiente de las tareas de servicio.

Por defecto, el correo de los flujos requiere a la vez `EMAIL_NOTIFICATIONS_ENABLED=true` en n8n y `data.notification_allowed=true`. Solo se utiliza `ALERT_RECIPIENT` fijo; un evento no puede elegir destinatarios. El correo de n8n sirve para notificar al equipo del proyecto; el backend maneja correos individuales conforme a preferencias. Evitar configurar el mismo buzón en ambos canales si se quiere un solo mensaje.

La deduplicación del evento se realiza antes del correo. Si el proceso cae entre registrar el evento y SMTP, el operador debe inspeccionar la ejecución fallida y reintentar la entrega con criterio; no hay garantía de exactamente una entrega. Los correos no incluyen enlaces sospechosos. HTTP tiene timeout 15 s y hasta 2 intentos. La aceptación inicial del webhook n8n no significa que todo el flujo haya terminado: revisar ejecuciones fallidas y callbacks de auditoría. Las ejecuciones correctas no conservan entrada; los errores deben purgarse según la retención del entorno.

Prueba reproducible de runtime: instalar la CLI fijada `n8n@2.44.4` y ejecutar `N8N_BIN=/ruta/a/n8n python automations/n8n/verify_flows.py`. La prueba crea una base SQLite temporal, importa credenciales y cuatro flujos, los publica mediante CLI y comprueba webhooks HTTP, autenticación, cron y deduplicación con un receptor local **simulado**; no usa SMTP ni proveedores. Para la publicación por CLI fija `N8N_USE_WORKFLOW_PUBLICATION_SERVICE=false` en esa instancia aislada: la CLI de esta versión actualiza el estado de publicación antiguo. En el despliegue normal la publicación se realiza desde el editor y no requiere esa opción.

Prueba con servicios locales reales: `N8N_BIN=/ruta/a/n8n backend/.venv/bin/python automations/n8n/verify_local_services.py` conecta a la API de desarrollo y PostgreSQL local y envía un mensaje únicamente a Mailpit (`127.0.0.1:1025`, destinatario `pruebas@ejemplo.invalid`). Se ejecutó satisfactoriamente: evento y callback persistidos en PostgreSQL, un mensaje recibido por Mailpit y cero correos enviados por Internet. Solo debe usarse con datos académicos locales; crea marcadores de integración y el correo de prueba. No modifica `.env`. Consultar [evidencia detallada](../automations/VERIFICATION.md).

Fuentes: [importar/exportar flujos](https://docs.n8n.io/build/manage-workflows/export-and-import.md), [Webhook](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook), [Schedule Trigger](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger), [Send Email](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.sendemail).

## Gmail por entorno y Mailpit local

Desarrollo utiliza Mailpit (`SMTP_HOST=mailpit`, `SMTP_PORT=1025`, sin usuario/clave/TLS dentro de la red Docker). La bandeja de prueba es local; no requiere ni envía desde Gmail. El usuario conectará su cuenta Gmail posteriormente. No se leen correos del usuario automáticamente; el análisis de mensajes recibe texto pegado explícitamente en la interfaz.

Para Gmail SMTP configurar `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_STARTTLS=true`, `SMTP_SSL=false`, `SMTP_USERNAME`, `SMTP_PASSWORD` mediante contraseña de aplicación de una cuenta con verificación en dos pasos, y remitente autorizado `SMTP_FROM`. Alternativa 465 con `SMTP_SSL=true` y `SMTP_STARTTLS=false`. La disponibilidad de contraseñas de aplicación depende de la política de la cuenta; OAuth2 sería una evolución si no están permitidas. No usar la contraseña normal de Gmail. Las credenciales n8n se vuelven a importar después de cambiar el entorno, sin publicar secretos.

Antes de habilitar envío real revisar en README el entorno activo, receptor y controles de notificación. La conexión Gmail interactiva del asistente no equivale a credenciales SMTP de la aplicación. Fuentes: [SMTP de Gmail](https://developers.google.com/workspace/gmail/imap/imap-smtp), [contraseñas de aplicación](https://support.google.com/accounts/answer/185833).

## Estado verificable

- Nueve pruebas offline de LCEL pasan con modelos simulados: desactivación, clave ausente, presupuesto, minimización, cuatro etapas, rechazo de evidencia inventada y timeout sin reintentos y construcción del adaptador OpenAI real sin invocar la API.
- Export Langflow construido e importado por LFX real; cuatro etapas ejecutadas contra receptor local controlado que informa IA no disponible.
- n8n 2.44.4: importación y publicación reales de cuatro flujos en base aislada; webhooks autenticados, A → B para crítico, cron real C, ingreso D y deduplicación pasaron contra backend HTTP controlado. Se observaron 10 solicitudes autenticadas, 2 callbacks de omisión y 2 resúmenes programados; se enviaron 0 correos. La prueba empleó el modo de publicación CLI compatible indicado arriba.
- Integración local adicional: n8n A → FastAPI real → PostgreSQL real → Mailpit SMTP real pasó con un mensaje académico local y callback `accepted` persistido. Langflow → API real pasó con sus cuatro etapas desactivadas y autenticadas.
- OpenAI, SMTP Gmail y VirusTotal reales requieren credenciales/consentimiento configurados; no se declara prueba real de esos proveedores.
- La verificación de contenedores y publicación Vercel requiere el entorno de despliegue del usuario.
