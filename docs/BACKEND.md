# Operación del backend

La API FastAPI y el worker son procesos separados que comparten PostgreSQL. Las migraciones Alembic son la fuente de cambios del esquema; no se ejecuta `create_all` al arrancar la aplicación. El esquema representa una organización académica de 10–20 usuarios. Los tres roles iniciales son fijos y sus asignaciones se administran mediante la API.

## Arranque y pruebas

Desde `backend/`, con las dependencias instaladas y el `.env` raíz configurado:

```bash
alembic upgrade head
python -m app.seed
uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
python -m app.worker
```

`DATABASE_URL` debe apuntar a PostgreSQL. La cuenta inicial se crea una sola vez; repetir `seed` no sobrescribe su contraseña. En Docker, las instrucciones equivalentes están en el README principal. `/health` comprueba la conexión con la base de datos. La documentación OpenAPI está en `/api/docs` durante desarrollo y se deshabilita en producción.

```bash
pytest -q
TEST_DATABASE_URL=postgresql+psycopg://usuario:clave@localhost:5432/vigia_tests pytest -q
```

La primera orden usa SQLite únicamente en pruebas de unidad y API. La segunda ejecuta las mismas rutas sobre PostgreSQL y añade pruebas de concurrencia de cuotas, reserva de presupuesto y `SKIP LOCKED`. Cada prueba crea y elimina su propio esquema: la cuenta de pruebas requiere permisos `CREATE SCHEMA`. Usar una base de pruebas separada. Los proveedores externos se simulan explícitamente; estos tests no acreditan una llamada real a OpenAI, VirusTotal ni Gmail.

## Sesiones, roles y MFA

Las contraseñas se almacenan con Argon2id. El token de acceso JWT dura `ACCESS_TOKEN_MINUTES`; el refresh opaco se conserva como hash en PostgreSQL y se rota en cada renovación, dentro de una cookie HttpOnly. Cada acceso comprueba la vigencia de la sesión y el estado actual de la cuenta. Desactivar o cambiar el rol de una cuenta revoca sus sesiones. Los límites de intentos persisten en la base de datos.

Administrador y analista deben matricular TOTP por defecto. Mientras la matrícula esté pendiente solo están disponibles perfil, configuración MFA y cierre de sesión. El secreto se cifra con Fernet y los códigos de recuperación se conservan como hashes de un solo uso. Se rechaza la reutilización de un mismo intervalo TOTP. Matricular MFA revoca las otras sesiones. Recuperar la contraseña por correo revoca las sesiones y conserva MFA.

Para entregar una instalación de desarrollo después de una revisión con MFA ya matriculado:

```bash
python -m app.seed reset-mfa --email admin@vigia.local --confirm
```

Este comando solo funciona con `ENVIRONMENT=development`, exige una cuenta administrativa existente, revoca sus sesiones y registra el restablecimiento en auditoría. La contraseña no cambia y el próximo acceso exige nueva matrícula. No está disponible en producción.

En producción: `COOKIE_SECURE=true`, `PUBLIC_APP_URL` y orígenes CORS HTTPS explícitos; no se admiten comodines. Con frontend y API en dominios distintos, `COOKIE_SAMESITE=none` requiere HTTPS y puede verse limitado por políticas de cookies de terceros del navegador. Preferir el proxy del despliegue Vercel para mantener `/api/v1` bajo el origen del frontend. Autorizar por separado el origen exacto de la extensión.

## Evaluaciones y cola durable

La heurística inicial trabaja en memoria y no visita la URL. Solo se persisten dominio, presentación redactada e indicadores. El texto de mensajes, rutas originales, consultas y fragmentos no se guardan. El límite diario de evaluaciones se comprueba bajo bloqueo de la fila del usuario, para serializar peticiones concurrentes y lotes.

Sin consentimiento externo, o sin proveedores habilitados, el resultado final es **no concluyente** y conserva la evaluación local. Con consentimiento explícito se encola el enriquecimiento. El worker vuelve a comprobar ese consentimiento antes de consultar a un proveedor. La reputación consulta únicamente el dominio y la IA recibe indicadores minimizados y contadores históricos acotados al acceso del solicitante. El modelo no controla la puntuación ni ejecuta acciones de gestión.

Las cuotas de VirusTotal y las reservas diarias de llamadas/tokens de IA son persistentes y se toman antes de la llamada. Una llamada fallida consume la reserva: reiniciar el worker no reinicia el presupuesto. El límite monetario real debe fijarse también en la cuenta del proveedor.

Los trabajos se reclaman con `FOR UPDATE SKIP LOCKED`, tienen un arrendamiento temporal y vuelven a intentarse con espera exponencial. Un trabajo interrumpido puede recuperarse al vencer `JOB_LEASE_SECONDS`. Al agotar `JOB_MAX_ATTEMPTS` queda en `failed`; un reporte termina en `failed` y una evaluación en `inconclusive`. La auditoría y los errores persistidos no contienen cuerpos de excepciones de los proveedores.

Las alertas e incidentes de riesgo alto se deduplican por evaluación. El enriquecimiento actualiza el texto de la alerta y puede elevar la severidad del incidente; conserva un escalamiento manual más alto.

## Notificaciones y automatizaciones

SMTP y el webhook fijo se entregan mediante la misma cola. La entrega es **al menos una vez**: una interrupción posterior a la aceptación remota puede provocar un reintento. Los correos usan un `Message-ID` estable y los webhooks un `event_id` estable. Una respuesta SMTP satisfactoria significa aceptación por el servidor, no prueba de lectura o entrega final. Los reportes distinguen envío pendiente, error y aceptación por el servicio.

Las preferencias y políticas se vuelven a comprobar al procesar las notificaciones. Los correos de recuperación de acceso siguen disponibles aunque se deshabiliten las notificaciones de alertas. Gmail requiere configurar SMTP y credenciales locales apropiadas al entorno; conectar Gmail en el chat no configura el contenedor.

Las integraciones entrantes requieren `X-Webhook-Key` y deduplican persistentemente sus eventos. No reciben una URL de callback arbitraria. El destino saliente procede exclusivamente de `OUTBOUND_WEBHOOK_URL` y no se siguen redirecciones.

## Reportes y privacidad

Los archivos PDF, DOCX y XLSX se generan en el worker y se guardan como bytes en PostgreSQL, no en una carpeta pública. La descarga exige Bearer y solo permite al solicitante. Un reporte conserva el alcance de su solicitud: promover al usuario no amplía un reporte propio y degradarlo impide descargar reportes organizacionales anteriores. Los períodos, filtros y límites se aplican antes de renderizar.

`GET /privacy/export` exporta los datos propios. `POST /privacy/requests` registra solicitudes ARCO; los mensajes se cifran. El administrador puede consultar `GET /privacy/requests` y procesarlas con:

```http
PATCH /api/v1/privacy/requests/{id}
Authorization: Bearer ...
Content-Type: application/json

{"status":"processing","note":"Se está verificando la identidad","erase_evaluations":false}
```

Los estados administrativos son `processing`, `completed` y `rejected`. La rectificación utiliza además los endpoints de perfil/administración; la oposición puede atenderse revocando las notificaciones y desactivando la cuenta según la solicitud. Solo una cancelación marcada `completed` con `erase_evaluations=true` ejecuta borrado: elimina evaluaciones y trabajos vinculados, invalida reportes que podrían contener esos datos, anonimiza y desactiva la cuenta y revoca sus sesiones. No permite cancelar directamente una cuenta administrativa activa. La identidad y el alcance deben verificarse por el responsable antes de ejecutar esa opción.

La purga se ejecuta cada hora en el worker, de acuerdo con la política de retención configurada. Elimina evaluaciones vencidas con sus alertas e incidentes, reportes y trabajos terminados vencidos, auditoría vencida, sesiones/tokens/cachés caducados y solicitudes ARCO resueltas vencidas. Invalida también los reportes que podrían conservar copias de evaluaciones eliminadas. Las solicitudes ARCO pendientes requieren atención administrativa. El responsable debe aplicar el mismo plazo a copias de seguridad y exportaciones fuera de la aplicación.

La minimización, el control de acceso y las solicitudes ARCO apoyan el tratamiento conforme a la Ley 29733; no equivalen a una certificación legal de cumplimiento de todos los procesos de una institución.
