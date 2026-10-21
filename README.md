# Vigía Financiera

MVP académico para 10–20 usuarios que evalúa **indicadores de riesgo** de phishing financiero. Incluye consola React en español inspirada en herramientas SOC, API FastAPI, PostgreSQL, extensión Chromium MV3, motor heurístico, adaptador VirusTotal, agentes LangChain, flujo Langflow, automatizaciones n8n y reportes PDF, DOCX y XLSX.

No garantiza que una URL sea segura ni identifica inequívocamente un hackeo. No recopila formularios, credenciales bancarias, OTP bancarios o tarjetas. El código MFA de Vigía se utiliza exclusivamente para autenticar la cuenta de esta plataforma.

![Consola Vigía Financiera](docs/evidence/dashboard.png)

## Inicio con Docker

Requisitos: Docker Engine accesible, Docker Compose v2+, Git y Python 3.11+ para generar configuración. Reserva recursos adicionales si activas Langflow/n8n; el stack básico no los necesita para clasificar URLs.

```bash
python3 scripts/init_env.py
docker compose up --build -d
docker compose ps
```

El inicializador crea `.env` con secretos aleatorios, permisos 600 y sin sobrescribir valores existentes. `.env.example` contiene la configuración documentada y ningún secreto real. **No publiques `.env` ni copies secretos a variables `VITE_`.**

Abre [la aplicación](http://localhost:8080), [la documentación API](http://localhost:8000/api/docs) y [el buzón de pruebas](http://localhost:8025). El administrador inicial y su contraseña están en `BOOTSTRAP_ADMIN_EMAIL` y `BOOTSTRAP_ADMIN_PASSWORD` de `.env`; consúltalos localmente. El primer acceso obliga a matricular TOTP para administrador y analista. Usa un autenticador compatible y guarda los códigos de recuperación una sola vez. Los usuarios finales son creados desde Administración, no hay registro público.

```bash
docker compose logs --tail=100 api worker
docker compose down
# Conserva los volúmenes. No uses down -v si necesitas conservar la información.
```

Las migraciones y el alta inicial son un servicio de arranque; no se reemplaza la contraseña de un administrador existente. Las evaluaciones, jobs, cuotas, caché y documentos se guardan en PostgreSQL. El worker es necesario para generar reportes y enriquecer evaluaciones.

## Configuración por entorno

| Grupo | Variables principales |
|---|---|
| Identidad visual | `APP_NAME`, `VITE_APP_NAME`, `VITE_APP_SHORT_NAME`, `VITE_ORGANIZATION`, `VITE_ACCENT_COLOR` |
| Persistencia y seguridad | `DATABASE_URL`, `POSTGRES_*`, `JWT_SECRET`, `FIELD_ENCRYPTION_KEY`, `REQUIRE_MFA_ROLES`, `COOKIE_*`, `CORS_ORIGINS` |
| Motor | `BANK_DOMAINS_JSON`, `RISK_*_THRESHOLD`, `RETENTION_DAYS`, `EVALUATION_DAILY_LIMIT` |
| VirusTotal | `VIRUSTOTAL_ENABLED`, `VIRUSTOTAL_API_KEY`, `REPUTATION_*` |
| IA | `AI_ENABLED`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `AI_*` |
| Correo | `SMTP_*`, `EMAIL_NOTIFICATIONS_ENABLED` |
| Automatizaciones | `WEBHOOK_SHARED_KEY`, `OUTBOUND_WEBHOOK_URL`, `WEBHOOK_NOTIFICATIONS_ENABLED`, `N8N_EMAIL_ENABLED`, `ALERT_RECIPIENT` |
| Extensión | `EXTENSION_API_BASE`, `EXTENSION_ORIGIN`, `EXTENSION_CACHE_SECONDS`, `EXTENSION_TIMEOUT_MS` |
| Despliegue | `PUBLIC_APP_URL`, `DEPLOYMENT_API_ORIGIN`, `VITE_API_BASE_URL` |

Las variables `VITE_*` son públicas y se incorporan durante build: reconstruye `web` después de cambiarlas. El resto requiere recrear los servicios afectados. La zona horaria de cada cuenta se detecta desde el navegador en el primer acceso y puede cambiarse en Mi cuenta; los registros se almacenan en UTC. `AUTOMATION_TIMEZONE` es exclusivamente la zona de programación de n8n.

## VirusTotal y OpenAI

VirusTotal consulta informes ya existentes del dominio, con consentimiento explícito por evaluación. No envía rutas, parámetros ni fragmentos y no solicita escaneos de URLs. Caché de seis horas y cuota conservadora de 450 solicitudes/día con intervalo mínimo de 16 segundos; un 429 o un fallo conserva el análisis local. Usa esta integración dentro de las condiciones académicas/no comerciales de tu plan público. Configura la clave en `.env`, nunca en el frontend o la extensión.

OpenAI está **deshabilitado de inicio**. Añade tu API key localmente, verifica un modelo disponible en tu cuenta y activa `AI_ENABLED=true`. Se conservó `OPENAI_MODEL=gpt-6-mini` como nombre solicitado, pero su disponibilidad exacta no se confirmó en la documentación oficial consultada; si la API lo rechaza, configura un modelo económico compatible con salida JSON estructurada. El sistema informará el fallo y mantendrá el score determinístico. No hay una llamada OpenAI real acreditada sin credencial configurada. VirusTotal sí se verificó con una consulta real del dominio público oficial de BCP; la evidencia está en QUALITY.md.

La base reserva cuotas de llamadas y tokens antes de invocar; hay un límite de cuatro etapas por evaluación y un timeout global. **Estos límites no son una garantía monetaria**: fija también un presupuesto en la cuenta del proveedor. La IA no modifica la puntuación y no tiene herramientas para navegar, ejecutar comandos o administrar el sistema.

## Gmail y notificaciones

En desarrollo se usa Mailpit: captura mensajes localmente y no los entrega a Internet. La plataforma no depende de conectar tu Gmail al chat. Para usar Gmail desde Docker, configura una cuenta autorizada y su credencial SMTP en **ese entorno**: `SMTP_HOST=smtp.gmail.com`, puerto 587 con `SMTP_STARTTLS=true`, o 465 con `SMTP_SSL=true`. Usa una contraseña de aplicación habilitada por tu cuenta o un mecanismo SMTP autorizado; no uses tu contraseña normal. No pongas ambos mecanismos TLS a la vez.

En un servidor vuelve a configurar las credenciales, conectividad de salida, identidad del remitente y preferencias. Si tu cuenta no admite contraseñas de aplicación, necesitas configurar OAuth en n8n o un relay autorizado: este MVP no incorpora un flujo OAuth de Gmail propio. La conexión del plugin Gmail de Codex es independiente del SMTP del software.

Hay cuatro canales: centro de alertas web, badge/notificaciones opcionales de extensión, SMTP y webhooks. El envío externo se procesa mediante outbox durable con reintentos; SMTP ofrece entrega al servidor, no confirmación de lectura. Las preferencias de usuario y política limitan los avisos.

## Extensión Chrome y Edge

1. Con el entorno Python del backend instalado, ejecuta `backend/.venv/bin/python scripts/configure_extension.py` para copiar únicamente valores públicos desde `.env`.
2. Abre `chrome://extensions` o `edge://extensions`, activa modo desarrollador y carga la carpeta `extension` sin empaquetar.
3. Copia su ID a `EXTENSION_ORIGIN=chrome-extension://ID` en `.env` y recrea API. La extensión usa permisos concedidos para un origen API concreto; no habilites CORS universal.
4. Abre el popup, guarda API/aplicación, concede el permiso para la API e inicia sesión con una cuenta de Vigía. Matricula MFA desde la web antes si corresponde.
5. Evalúa la pestaña activa. El automático y las notificaciones se habilitan expresamente desde botones separados. El automático puede desactivarse y sus permisos revocarse.

Solo se envía el **origen** del sitio; las rutas privadas no salen del navegador. La sesión se guarda en `chrome.storage.session`, caduca y requiere iniciar sesión nuevamente. La extensión no lee contenido de formularios, no inspecciona todo el tráfico HTTPS y no bloquea automáticamente. Hay caché por origen y actualización progresiva acotada; consulta el historial web para un análisis que continúe pendiente.

## n8n y Langflow

```bash
docker compose --profile integrations up --build -d
docker compose exec n8n node /flows/bootstrap.cjs
```

Abre n8n en [localhost:5678](http://localhost:5678) y completa su configuración de propietario. El bootstrap importa credenciales desde entorno y cuatro workflows **inactivos**. Revisa los destinatarios y activa/publica los flujos A–D. Para recibir alertas del worker habilita `WEBHOOK_NOTIFICATIONS_ENABLED=true` y la política correspondiente. El correo de los workflows requiere además `N8N_EMAIL_ENABLED=true`; por defecto no envía nada.

Langflow se abre en [localhost:7860](http://localhost:7860) con las credenciales de `.env`. Importa `automations/langflow/vigia-evidence-agents.json`. El puente usa una URL interna fija y la misma cuota persistente de la API. No introduzcas la clave OpenAI en un flujo exportado. Procedimientos y resultados de verificación en [INTEGRATIONS.md](docs/INTEGRATIONS.md).

Los editores son superficies administrativas con capacidad de ejecutar flujos: mantenlos en localhost o detrás de control de acceso. No deben publicarse como parte de la consola de usuarios.

## Vercel

La configuración entregada despliega el **frontend** en Vercel y lo conecta por proxy del mismo origen a una API Docker pública HTTPS. PostgreSQL, worker, n8n, Langflow y SMTP necesitan infraestructura persistente; no son sustituidos por hosting estático. No se publicó un despliegue ni se crearon recursos en tu cuenta.

1. Despliega el stack Docker en un servidor y publica solamente web/API a través de un proxy HTTPS. El Compose de desarrollo publica puertos en localhost; adapta el proxy de entrada del servidor.
2. En `.env`, configura `DEPLOYMENT_API_ORIGIN=https://ORIGEN-DE-TU-API`, sin ruta ni credenciales. Ejecuta `backend/.venv/bin/python scripts/configure_vercel.py`. El script genera rewrites sin copiar secretos.
3. Importa este repositorio como proyecto Vercel con **Root Directory en la raíz del repositorio**, framework Vite, build e install definidos por `vercel.json`. El dominio gratuito `.vercel.app` basta para el frontend.
4. Conserva `VITE_API_BASE_URL=/api/v1`. Configura los `VITE_*` públicos en Vercel y en backend `ENVIRONMENT=production`, `PUBLIC_APP_URL=https://TU-PROYECTO.vercel.app`, `CORS_ORIGINS` con ese origen y `COOKIE_SECURE=true`. El proxy de mismo origen permite refresh HttpOnly sin depender de cookies de terceros.
5. Verifica login/MFA, recarga de sesión, análisis, historial y descarga contra esa URL antes de considerar verificado el despliegue. En el entorno de producción configura de nuevo SMTP, proveedores, backups y secretos. `EXTENSION_API_BASE` necesita la API pública HTTPS y permiso de origen.

Sin `DEPLOYMENT_API_ORIGIN`, el archivo queda preparado para construir el frontend pero no inventa una API pública. Las credenciales Vercel y el servidor destino no fueron proporcionados, de modo que la configuración cloud está pendiente de validación en tu cuenta.

## Desarrollo y pruebas

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.lock
cd frontend
npm ci
npm test
npm run build
```

Para desarrollar sin contenedores, usa PostgreSQL propio, configura `DATABASE_URL`, ejecuta desde `backend`: `alembic upgrade head`, `python -m app.seed`, `uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log` y `python -m app.worker` en otra terminal. Desde `frontend`, `npm run dev -- --host 127.0.0.1`. Usa **localhost:5173** o añade el origen alternativo explícitamente a CORS; mezclar localhost y 127.0.0.1 afecta cookies/orígenes.

```bash
# Desde backend; TEST_DATABASE_URL debe apuntar a una base desechable propia.
TEST_DATABASE_URL=postgresql+psycopg://USUARIO:CLAVE@localhost:5432/vigia_tests .venv/bin/python -m pytest -q
# Sin TEST_DATABASE_URL: pruebas locales SQLite, no equivalen a integración PG.
cd ../extension
node --test tests/*.test.js
```

El test de PostgreSQL crea y elimina esquemas aleatorios propios, no borra la base de aplicación. Las pruebas usan proveedores/SMTP simulados salvo evidencia explícita. El E2E de navegador crea cuentas y evaluaciones controladas; ejecútalo sobre un entorno de prueba: `cd frontend && npx playwright install chromium && npm run test:e2e`. Consulta [QUALITY.md](docs/QUALITY.md) para resultados, comandos y fronteras pendientes.

Para repetir el benchmark offline, consulta [data/README.md](data/README.md). No abras las URLs del dataset. La muestra histórica global evidenció una limitación severa del motor local: no se debe usar como protección general autónoma; reputación y revisión humana son esenciales. Las demostraciones usan `.invalid`.

## Documentación

- [Análisis y arquitectura](docs/DESIGN.md), [contratos](docs/CONTRACT.md), [diccionario de datos](docs/DATA_DICTIONARY.md), [OpenAPI real](docs/openapi.json).
- [Manual de usuario](docs/USER_GUIDE.md), [operación y respaldo](docs/ADMIN_GUIDE.md), [backend](docs/BACKEND.md).
- [Reglas de puntuación](docs/SCORING.md), [privacidad y Ley 29733](docs/PRIVACY.md), [integraciones](docs/INTEGRATIONS.md).
- [Identidad visual](docs/BRAND.md), [calidad y limitaciones](docs/QUALITY.md).

En este entorno `.git` es un directorio vacío protegido por la aplicación. Se inicializó Git usando metadatos en `.git-local`: `sh scripts/git-local.sh status`. Al llevar el proyecto a un directorio normal puede inicializarse un repositorio Git convencional. No se subió código, no se hizo commit de secretos ni se creó un remoto.
