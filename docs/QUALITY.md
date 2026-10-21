# Calidad y estado de entrega

Verificación local del 21 de octubre de 2026. Las afirmaciones de esta entrega se apoyan en comandos ejecutados y archivos de evidencia; un servicio externo sin credenciales o un contenedor no iniciado no se declara operativo por tener configuración.

## Resultado comprobado

| Área | Resultado | Evidencia |
|---|---|---|
| Backend y seguridad | 96 pruebas completas sobre PostgreSQL; además pasó la regresión adicional de fechas con offset en reportes (15 casos de reportes en su pase específico). Incluyen API, MFA, roles, aislamiento, Unicode privado, reanálisis, reportes largos, concurrencia, lease y retención | `evidence/backend-junit.xml`, tests backend |
| Frontend | 8 pruebas unitarias, TypeScript y build Vite aprobados | `FRONTEND_QA.md` |
| Extensión | 2 pruebas de privacidad aprobadas; carga real MV3, service worker y popup sin errores con permisos opcionales ausentes | `extension/tests/privacy.test.js`, `evidence/extension.png` |
| Navegador integral | Login/MFA→análisis→historial→alerta/incidente→PDF/DOCX/XLSX; roles, preferencias, ARCO, recarga de sesión y móvil aprobados con API/PG/worker reales | `evidence/frontend-e2e-final.txt` |
| VirusTotal | Una consulta real de informe del dominio público oficial viabcp.com fue available; 0 detecciones maliciosas/0 sospechosas. Esto no garantiza legitimidad | `evidence/virustotal-live.json` |
| LangChain | 9 pruebas incluidas en suite backend, modelo simulado y adaptador real construido sin consumir OpenAI | `automations/VERIFICATION.md` |
| Langflow | JSON 6 nodos/5 conexiones importado y ejecutado por LFX 0.2.2 real; 4 etapas contra receptor controlado y luego contra FastAPI local real; IA disabled explícita | `automations/VERIFICATION.md` |
| n8n | 4 workflows importados y ejecutados en n8n 2.44.4 real, auth, cron, A→B, D e idempotencia con receptor controlado | `automations/VERIFICATION.md` |
| n8n/SMTP integral | A→API real→PostgreSQL→Mailpit: 1 mensaje local a una dirección académica `.invalid`, callback accepted persistido, 0 correos a Internet | `automations/VERIFICATION.md` |
| Migraciones | 3 revisiones aplicadas a base vacía PostgreSQL 18.6; alembic check sin operaciones nuevas | revisiones Alembic y verificación ejecutada |
| Respaldo | pg_dump custom y pg_restore sobre base separada vacía; datos restaurados, 10 claves foráneas y MFA cifrado legible con la clave correspondiente | `evidence/backup-restore.json` |
| Dependencias | pip-audit y npm audit: 0 vulnerabilidades conocidas tras actualizar las versiones afectadas | `evidence/dependency-audit.json`, `evidence/frontend-audit.json` |
| Docker | Compose schema válido; Dockerfiles y perfiles configurados. El daemon del equipo negó acceso al socket incluso fuera del sandbox | `compose.yaml`; build/up **no verificados** |
| Vercel | Configuración frontend, build y generador de proxy HTTPS entregados; no se crearon recursos ni se desplegó en la cuenta | `vercel.json`, `scripts/configure_vercel.py`; **no desplegado** |

Las advertencias de PyMuPDF/SWIG sobre tipos internos no causaron fallos de pruebas. Una auditoría de dependencias sin avisos conocidos no demuestra ausencia total de vulnerabilidades; no se realizó pentest ni auditoría de imágenes Docker.

## Rendimiento y calidad de clasificación

La prueba real local creó 20 sesiones efímeras de usuarios de prueba distintos y envió 20 solicitudes simultáneas a FastAPI+PostgreSQL. Todas recibieron 201. Latencias HTTP: p50≈196.5 ms, p95≈219.2 ms, p99≈220.6 ms. Login interactivo se verificó por separado en navegador; estas cifras no incluyen Argon2/TOTP ni consultas externas. Los fixtures se eliminaron al terminar. Detalles y procedimiento en `scripts/verify_local.py` y `evidence/local-performance.json`.

El benchmark offline de 2000 URLs históricas de PhiUSIIL, con 1000 por clase y semilla fija, midió p95 heurística≈0.30ms y p99≈0.43ms en esta máquina. No se visitó ningún destino ni se consumieron proveedores durante esa prueba. Los tiempos de VirusTotal/OpenAI no se caracterizaron estadísticamente; no se publican percentiles inventados para esos servicios o para caché bajo carga.

**Limitación sustantiva:** a umbral 50, la heurística inicial detectó 1 de 1000 muestras de phishing genérico y produjo 0 de 1000 falsos positivos: recall 0.1%, falsos negativos 99.9%. El corpus global no representa específicamente banca peruana, pero muestra que estas reglas no bastan como detector general. El MVP es una plataforma de integración y evaluación explicable con foco acotado; no debe usarse como protección autónoma de navegación. Fuente, checksum, matriz y limitaciones en `evidence/dataset-benchmark.json` y `SCORING.md`. No se entrenó ni se presenta un modelo de ML propio.

## Reportes y revisión visual

Los tres formatos se generaron con datos de PostgreSQL y se descargaron con autorización desde la API. Se verificaron firma de archivo, texto, metadatos, filtros, gráficos, tablas y protección de fórmulas en Excel. El PDF divide filas largas; notas excesivas se abrevian de forma explícita en los documentos, no en el historial original. El gráfico consolidado cuenta evaluaciones sin sumar nuevamente sus alertas/incidentes. El PDF incluye fuentes TTF con licencia para evitar depender de las fuentes instaladas en el lector.

Las muestras finales pequeñas de `sample-report.*` provienen de una cuenta académica desechable y fueron regeneradas mediante `scripts/verify_local.py --reports-only` después de los ajustes de presentación. Se renderizaron y revisaron visualmente las dos páginas de PDF y las dos páginas de Word con fuentes y tablas finales mediante herramientas incluidas; las imágenes QA están en `evidence/`. Son ejemplos de salida editables, no datos de clientes reales. La evidencia de navegador anterior acredita además la descarga de reportes organizacionales consolidados.

## Estado por fase y aceptación

| Fase | Estado de código y evidencia | Pendiente real |
|---|---|---|
| 1 Análisis y diseño | Entregada: alcance, historias, arquitectura, ER, contratos y amenazas | Validación visual de identidad propuesta por el autor |
| 2 Infraestructura y backend | API/PG/migraciones/RBAC/MFA implementados y probados en host local | Ejecutar build/up del stack Docker con acceso al daemon |
| 3 Motor e inteligencia | Heurísticas, reputación, presupuesto, agentes y flujo reproducible verificados | OpenAI real con key/modelo disponible; ampliar eficacia de clasificación |
| 4 Frontend y extensión | Recorrido web y carga MV3 reales aprobados, capturas desktop/móvil | Permiso opcional manual y automático de extensión en el navegador personal; aviso de navegación completo no automatizado en esta sesión |
| 5 Automatizaciones y reportes | n8n, SMTP local, Langflow engine y 3 formatos verificados | Gmail real y UI completa Langflow dentro del contenedor |
| 6 Integración y entrega | Pruebas, auditorías, rendimiento, respaldo y manuales entregados | Despliegue cloud/HTTPS y humo completo del Compose; no se declara aceptación final universal |

AC01–AC09, AC11–AC13, AC15 y AC17 de DESIGN tienen evidencia de pruebas funcionales. AC10 tiene implementación, pruebas de privacidad y carga real de extensión; la interacción completa de permisos de navegación en un navegador personal sigue pendiente. AC14 se verificó en n8n real y SMTP local. AC16 está verificado sobre PostgreSQL real, incluyendo migraciones y jobs. El criterio final de arranque mediante contenedores queda pendiente por acceso al daemon. La funcionalidad externa está marcada según su prueba real, no inferida del adaptador.

## Reproducir

```bash
# Backend, desde backend/ y con PostgreSQL desechable propio
TEST_DATABASE_URL=postgresql+psycopg://USUARIO:CLAVE@localhost:5432/vigia_tests .venv/bin/python -m pytest -q
# Frontend y extensión, desde raíz
npm --prefix frontend test
npm --prefix frontend run build
node --test extension/tests/*.test.js
# Requiere stack activo y datos de prueba; nunca producción
npm --prefix frontend run test:e2e
npm --prefix frontend run test:extension
# Proveedores visuales, ver requisitos de entorno en sus cabeceras
N8N_BIN=/ruta/a/n8n python automations/n8n/verify_flows.py
python automations/langflow/verify_flow.py
```

El runner Node y TestClient requieren permisos de procesos/red local que esta sesión restringe por defecto; se ejecutaron fuera de esa restricción para obtener resultados completos. Los contenedores siguen sujetos a los permisos del daemon del sistema. Las pruebas locales no cambian las políticas de acceso de tu equipo.

Para repetir la prueba HTTP y las descargas usa `DATABASE_URL` de desarrollo local y `backend/.venv/bin/python scripts/verify_local.py`. Para la consulta VirusTotal real se consumió una llamada pública y se guardó la respuesta minimizada; no se visitó el sitio ni se enviaron rutas. OpenAI, Gmail y Vercel siguen sin prueba real. Se restableció el MFA administrativo de desarrollo y se eliminó la semilla temporal de navegador antes de la entrega; el propietario debe matricular su propio autenticador.
