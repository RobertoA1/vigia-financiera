# Operación y administración

## Arranque y configuración

Sigue el README: genera `.env`, configura secretos y ejecuta Docker Compose. `migrate` aplica Alembic y crea un administrador si aún no existe. El worker se inicia como proceso independiente; API y worker deben usar exactamente las mismas claves de firma/cifrado y base de datos. Cambiar `FIELD_ENCRYPTION_KEY` sin recifrar los campos existentes vuelve ilegibles MFA, solicitudes ARCO y correos pendientes.

Las variables de build del frontend son públicas; no son un almacén de secretos. Las URLs del backend y del dashboard deben usar HTTPS en producción. CORS acepta únicamente orígenes explícitos y nunca `*`. Para n8n por HTTP dentro de la red Docker de producción habilita `WEBHOOK_ALLOW_INTERNAL_HTTP=true` solo si mantienes el destino fijo `http://n8n:5678/webhook/vigia-alerts`; el backend no permite usar esa excepción para otros hosts o rutas. Para un destino externo utiliza HTTPS.

Los usuarios son creados con rol user, analyst o admin. Desactivar una cuenta y cambiar privilegios revoca sesiones cuando corresponde. Los roles son fijos; la gestión del MVP administra asignaciones, no crea políticas arbitrarias. Los documentos mantienen su alcance al generarse; un usuario degradado no conserva acceso a un reporte organizacional anterior.

## Datos y migraciones

```bash
docker compose run --rm migrate
docker compose exec api alembic current
docker compose exec api alembic check
```

No uses create_all como reemplazo de migraciones en despliegue. Las pruebas usan esquemas desechables y no certifican automáticamente que sea seguro aplicar cambios sobre una base de producción existente. Los tres archivos de migración iniciales crean tablas, preservan el alcance de reportes y agregan restricciones de integridad. Guarda un backup antes de una futura actualización y prueba su restauración en un entorno separado.

## Respaldo y recuperación

Ejemplo de backup lógico, desde la raíz del proyecto:

```bash
mkdir -p data/private/backups
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > data/private/backups/vigia.dump
```

Conserva los secretos de cifrado y la configuración en un almacén separado del dump. El volumen de PostgreSQL contiene reportes y jobs, no solo evaluaciones. Los volúmenes n8n y Langflow conservan sus configuraciones/credenciales por separado; expórtalos mediante sus herramientas y conserva sus claves de cifrado. Protege las copias en reposo, limita acceso y aplica una retención definida.

Para probar restauración usa una **base vacía distinta**, no la base en uso:

```bash
docker compose exec -T db sh -c 'createdb -U "$POSTGRES_USER" vigia_restore_check'
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d vigia_restore_check --no-owner --no-privileges' < data/private/backups/vigia.dump
```

Comprueba conteos, restricciones y lectura de campos cifrados usando las claves correspondientes. La orden no incluye `--clean` para evitar borrado inadvertido de datos existentes. Antes de restaurar para operación real, aplica el registro de supresiones ARCO y revisa reactivación de sesiones/jobs antiguos. El procedimiento de backup/restore está documentado; su resultado local verificado se detalla en QUALITY.

## Worker, cuotas y notificaciones

El worker reclama jobs con transacciones, lease y SKIP LOCKED. Un reinicio permite recuperar jobs vencidos; el máximo de intentos produce estado failed y auditoría. Las llamadas externas tienen timeout; SMTP/webhooks usan backoff persistente. Inspecciona `docker compose logs --tail=100 worker` y la consulta de estado del dashboard/automatizaciones. No expongas payloads originales ni trazas secretas en soporte.

VirusTotal público dispone de cuota limitada: la configuración es conservadora y compartida en PostgreSQL. Un resultado rate_limited requiere esperar o usar caché, no crear nuevas claves para evadir límites. La IA reserva llamadas/tokens antes de invocar. Ajusta los límites según cuota real y evalúa un presupuesto de cuenta del proveedor. Las reservas fallidas no se reembolsan automáticamente: esto evita reintentos que excedan presupuesto.

SMTP utiliza entrega al menos una vez. Un crash después de aceptación del servidor puede repetir un correo al reintentar; un Message-ID estable ayuda a correlacionar pero no garantiza exactamente una entrega. n8n registra primero el evento para deduplicarlo; una caída entre registro y envío puede requerir atención manual. Consulta ejecuciones y callbacks, no supongas que HTTP200 inicial confirma entrega de un mensaje.

## Recuperación administrativa de MFA en desarrollo

```bash
docker compose exec api python -m app.seed reset-mfa --email CUENTA-DE-PRUEBAS --confirm
```

El comando requiere `ENVIRONMENT=development`, una cuenta existente y confirmación explícita. Revoca sesiones y registra auditoría; no es un endpoint público ni una operación válida en producción. Se usa para devolver al usuario la matrícula de su propio autenticador tras pruebas de desarrollo. Nunca utilices semillas TOTP de pruebas en cuentas reales.

## Diagnóstico frecuente

| Síntoma | Comprobación y acción |
|---|---|
| Permiso denegado al socket Docker | El proceso no puede acceder al daemon; configura acceso según tu sistema y vuelve a ejecutar Compose. No se resuelve instalando solo el cliente |
| API no inicia | Revisa secretos obligatorios, disponibilidad de DB, migraciones, HTTPS/cookies/CORS y validación de configuración |
| Login funciona pero recarga no | Usa el mismo hostname; comprueba Origin, cookie HttpOnly/Secure/SameSite, proxy y URL pública |
| No aparecen reportes listos | Worker activo, jobs pendientes/fallidos, período/filas dentro de límites y usuario solicitante activo |
| No llega correo | Preferencias, política, SMTP_HOST por entorno, TLS correcto y Mailpit en desarrollo. Conectar Gmail al chat no configura SMTP |
| VirusTotal no concluye | Sin consentimiento, clave/activación ausente, cuota o informe inexistente; conservar evidencia local y revisar su motivo |
| IA no disponible | Falta clave, nombre de modelo no accesible, límites/timeout o schema rechazado; no se altera score por ello |
| n8n devuelve404 | Workflows importados pero no publicados, webhookId ausente en export viejo o rutas aún no registradas; usar JSON actual y publicar en UI |
| Extensión no conecta | Conceder permiso del origen API, configurar EXTENSION_ORIGIN, HTTPS remoto y sesión/MFA vigentes |
| Vercel muestra interfaz sin datos | DEPLOYMENT_API_ORIGIN vacío o API inaccesible desde cloud; regenerar proxy y verificar API pública HTTPS |

La observabilidad inicial incluye logs operacionales sin cuerpos de entrada, estado durable de jobs, auditoría y métricas agregadas. No incluye un stack externo de tracing/Prometheus ni certificación de operación 24/7.
