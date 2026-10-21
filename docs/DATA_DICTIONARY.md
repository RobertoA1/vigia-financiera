# Diccionario de datos

Generado desde los modelos finales. PostgreSQL utiliza timestamps con zona horaria; API conserva offset y reportes convierten explícitamente a UTC. Las claves de cifrado están fuera de la base. Organización única; no hay multi-tenancy. JSON conserva evidencia versionada y timelines; no reemplaza las claves de identidad y permisos.

## jobs

Cola/outbox durable. Reclamo con SKIP LOCKED, lease, intentos y backoff; correo pendiente cifrado.

| Campo | Tipo | Nulo | Clave y referencia |
|---|---|---|---|
| id | VARCHAR(36) | No | PK |
| kind | VARCHAR(32) | No | — |
| payload | JSON | No | — |
| status | VARCHAR(16) | No | — |
| attempts | INTEGER | No | — |
| available_at | DATETIME | No | — |
| locked_at | DATETIME | Sí | — |
| completed_at | DATETIME | Sí | — |
| last_error | VARCHAR(240) | Sí | — |
| created_at | DATETIME | No | — |

Índices: ix_jobs_available_at: available_at; ix_jobs_status: status.

Restricciones: `attempts >= 0`; `status IN ('pending','running','complete','failed')`; `kind IN ('evaluation','report','email','webhook')`.

## policies

Política singleton de la única organización: conservación y canales de notificación.

| Campo | Tipo | Nulo | Clave y referencia |
|---|---|---|---|
| id | INTEGER | No | PK |
| retention_days | INTEGER | No | — |
| email_notifications | BOOLEAN | No | — |
| webhook_notifications | BOOLEAN | No | — |

Restricciones: `retention_days >= 1 AND retention_days <= 3650`; `id = 1`.

## provider_budgets

Reservas de llamadas/tokens por proveedor y día UTC; intervalo mínimo reputacional.

| Campo | Tipo | Nulo | Clave y referencia |
|---|---|---|---|
| key | VARCHAR(80) | No | PK |
| calls | INTEGER | No | — |
| tokens | INTEGER | No | — |
| next_allowed_at | DATETIME | Sí | — |

Restricciones: `calls >= 0 AND tokens >= 0`.

## rate_limits

Contadores compartidos con ventana/caducidad para resistir procesos concurrentes.

| Campo | Tipo | Nulo | Clave y referencia |
|---|---|---|---|
| key | VARCHAR(64) | No | PK |
| count | INTEGER | No | — |
| reset_at | DATETIME | No | — |

Restricciones: `count >= 0`.

## reputation_cache

Evidencia pública de dominio con TTL compartida entre workers.

| Campo | Tipo | Nulo | Clave y referencia |
|---|---|---|---|
| domain | VARCHAR(253) | No | PK |
| payload | JSON | No | — |
| expires_at | DATETIME | No | — |

## users

Identidad, rol fijo, preferencias, zona IANA, contraseña Argon2 y configuración MFA cifrada.

| Campo | Tipo | Nulo | Clave y referencia |
|---|---|---|---|
| id | VARCHAR(36) | No | PK |
| email | VARCHAR(254) | No | Único |
| name | VARCHAR(120) | No | — |
| password_hash | TEXT | No | — |
| role | VARCHAR(16) | No | — |
| active | BOOLEAN | No | — |
| mfa_enabled | BOOLEAN | No | — |
| mfa_secret_encrypted | TEXT | Sí | — |
| pending_mfa_secret_encrypted | TEXT | Sí | — |
| pending_mfa_at | DATETIME | Sí | — |
| mfa_last_counter | INTEGER | No | — |
| recovery_code_hashes | JSON | No | — |
| timezone | VARCHAR(64) | Sí | — |
| email_notifications | BOOLEAN | No | — |
| browser_notifications | BOOLEAN | No | — |
| created_at | DATETIME | No | — |

Índices: ix_users_email: email.

Restricciones: `role IN ('admin','analyst','user')`; `mfa_enabled = false OR mfa_secret_encrypted IS NOT NULL`.

## webhook_events

Recibos idempotentes por event_id/tipo, resultado mínimo y callbacks de notificación.

| Campo | Tipo | Nulo | Clave y referencia |
|---|---|---|---|
| id | VARCHAR(36) | No | PK |
| event_id | VARCHAR(128) | No | — |
| kind | VARCHAR(40) | No | — |
| result | JSON | No | — |
| created_at | DATETIME | No | — |

## audit

Eventos críticos con actor opcional; SET NULL permite desidentificación sin perder registro operativo.

| Campo | Tipo | Nulo | Clave y referencia |
|---|---|---|---|
| id | VARCHAR(36) | No | PK |
| actor_id | VARCHAR(36) | Sí | FK users.id (SET NULL) |
| action | VARCHAR(80) | No | — |
| target_id | VARCHAR(80) | Sí | — |
| detail | JSON | No | — |
| created_at | DATETIME | No | — |

Índices: ix_audit_created_at: created_at; ix_audit_action: action.

## evaluations

Propietario, dominio minimizado y evidencia JSON versionada; sin URL cruda ni texto de mensajes.

| Campo | Tipo | Nulo | Clave y referencia |
|---|---|---|---|
| id | VARCHAR(36) | No | PK |
| user_id | VARCHAR(36) | No | FK users.id (CASCADE) |
| domain | VARCHAR(253) | No | — |
| url_display | TEXT | No | — |
| score | INTEGER | No | — |
| risk | VARCHAR(16) | No | — |
| status | VARCHAR(24) | No | — |
| source | VARCHAR(24) | No | — |
| external_consent | BOOLEAN | No | — |
| evidence | JSON | No | — |
| created_at | DATETIME | No | — |
| updated_at | DATETIME | No | — |

Índices: ix_evaluations_user_id: user_id; ix_evaluations_created_at: created_at; ix_evaluations_risk: risk; ix_evaluations_status: status; ix_evaluations_domain: domain.

Restricciones: `risk IN ('low','moderate','high','critical')`; `score >= 0 AND score <= 100`; `status IN ('preliminary','complete','pending','inconclusive')`; `source IN ('manual','extension','email','sms','api')`.

## privacy_requests

Solicitudes ARCO con mensaje cifrado y estado de atención.

| Campo | Tipo | Nulo | Clave y referencia |
|---|---|---|---|
| id | VARCHAR(36) | No | PK |
| user_id | VARCHAR(36) | No | FK users.id (CASCADE) |
| kind | VARCHAR(24) | No | — |
| message_encrypted | TEXT | No | — |
| status | VARCHAR(24) | No | — |
| created_at | DATETIME | No | — |

Índices: ix_privacy_requests_user_id: user_id.

Restricciones: `kind IN ('access','rectification','cancellation','opposition')`; `status IN ('pending','processing','completed','rejected')`.

## recovery_tokens

Recuperación de contraseña de un solo uso con hash y caducidad; no deshabilita MFA.

| Campo | Tipo | Nulo | Clave y referencia |
|---|---|---|---|
| id | VARCHAR(36) | No | PK |
| user_id | VARCHAR(36) | No | FK users.id (CASCADE) |
| token_hash | VARCHAR(64) | No | Único |
| expires_at | DATETIME | No | — |
| used | BOOLEAN | No | — |

Índices: ix_recovery_tokens_user_id: user_id.

## reports

Artefactos autorizados. Contenido binario base64, filtros, estado y alcance own/organization persistido.

| Campo | Tipo | Nulo | Clave y referencia |
|---|---|---|---|
| id | VARCHAR(36) | No | PK |
| user_id | VARCHAR(36) | No | FK users.id (CASCADE) |
| kind | VARCHAR(24) | No | — |
| format | VARCHAR(8) | No | — |
| scope | VARCHAR(16) | No | — |
| status | VARCHAR(24) | No | — |
| filters | JSON | No | — |
| content | TEXT | Sí | — |
| error | TEXT | Sí | — |
| created_at | DATETIME | No | — |

Índices: ix_reports_user_id: user_id.

Restricciones: `status IN ('pending','complete','failed')`; `scope IN ('own','organization')`; `kind IN ('evaluations','alerts','incidents','consolidated')`; `format IN ('pdf','docx','xlsx')`.

## sessions

Sesiones revocables. Refresh hasheado, caducidad y estado de MFA; JWT refiere su id.

| Campo | Tipo | Nulo | Clave y referencia |
|---|---|---|---|
| id | VARCHAR(36) | No | PK |
| user_id | VARCHAR(36) | No | FK users.id (CASCADE) |
| refresh_hash | VARCHAR(64) | No | Único |
| mfa_complete | BOOLEAN | No | — |
| expires_at | DATETIME | No | — |
| revoked | BOOLEAN | No | — |
| created_at | DATETIME | No | — |

Índices: ix_sessions_user_id: user_id.

## alerts

Una alerta por evaluación; el riesgo y mensaje se actualizan con nueva evidencia.

| Campo | Tipo | Nulo | Clave y referencia |
|---|---|---|---|
| id | VARCHAR(36) | No | PK |
| evaluation_id | VARCHAR(36) | No | Único; FK evaluations.id (CASCADE) |
| user_id | VARCHAR(36) | No | FK users.id (CASCADE) |
| title | VARCHAR(240) | No | — |
| risk | VARCHAR(16) | No | — |
| message | TEXT | No | — |
| read | BOOLEAN | No | — |
| created_at | DATETIME | No | — |

Índices: ix_alerts_user_id: user_id.

Restricciones: `risk IN ('low','moderate','high','critical')`.

## incidents

Un incidente por evaluación, responsable opcional, severidad y timeline de acciones.

| Campo | Tipo | Nulo | Clave y referencia |
|---|---|---|---|
| id | VARCHAR(36) | No | PK |
| evaluation_id | VARCHAR(36) | No | Único; FK evaluations.id (CASCADE) |
| title | VARCHAR(240) | No | — |
| severity | VARCHAR(16) | No | — |
| status | VARCHAR(24) | No | — |
| assigned_to | VARCHAR(36) | Sí | FK users.id (SET NULL) |
| timeline | JSON | No | — |
| created_at | DATETIME | No | — |
| updated_at | DATETIME | No | — |

Índices: ix_incidents_status: status.

Restricciones: `status IN ('open','investigating','resolved','dismissed')`; `severity IN ('low','moderate','high','critical')`.
