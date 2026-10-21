# Verificación del frontend y la extensión

Verificado el 21 de octubre de 2026 contra la API FastAPI real, PostgreSQL local y worker de reportes. Navegador Chromium instalado en el sistema, ejecutado mediante Playwright. No se emplearon respuestas simuladas en las pruebas de navegador. Los datos de evidencia corresponden a dominios controlados `.invalid`; no se visitaron destinos sospechosos ni se activó el consentimiento externo.

| Frontera | Evidencia comprobada |
| --- | --- |
| Acceso y MFA | Inicio de sesión, configuración QR/TOTP y confirmación; actualización de sesión por cookie HttpOnly después de recargar |
| Captura y análisis | Formulario URL, extracción de enlaces desde texto, consentimiento externo desactivado inicialmente, borrado del texto en memoria tras procesar, visualización redactada |
| Evidencia | Filtro de historial, detalle con URL no navegable, indicadores y recomendaciones |
| Operación | Lectura de alertas; cambio de estado de incidente con nota e historial |
| Reportes | Generación con worker y descarga autenticada de PDF, DOCX y XLSX; comprobación de firma del formato y contenido no vacío |
| Administración | Creación de usuario mediante interfaz, verificación de vistas y permisos del usuario final |
| Preferencias | Detección inicial de America/Lima desde el navegador y cambio persistido a Europe/Madrid en cuenta de prueba |
| Privacidad | Solicitud ARCO de acceso del usuario, exportación de sus datos, atención administrativa y respuesta |
| Sesión web | Sin tokens en localStorage/sessionStorage; caché de datos separada por usuario; cero errores JavaScript en el recorrido completo |
| Diseño adaptable | Capturas de escritorio 1440 px y móvil 390 px, sin desbordamiento de la página; tablas con desplazamiento horizontal y navegación móvil |
| Extensión MV3 | Carga real unpacked, service worker y popup sin errores con webNavigation/notifications todavía no concedidos; sin token, análisis automático ni consentimiento externo por defecto |

La prueba automatizada de navegador está en `frontend/e2e/smoke.mjs` (`npm --prefix frontend run test:e2e`); requiere API, PostgreSQL y worker activos, Chromium/Playwright disponible y credenciales iniciales de `.env`. Genera cuentas y evidencia académica. Conserva temporalmente la semilla TOTP de la cuenta de pruebas fuera del repositorio con permisos 0600 para repetir la prueba, y nunca la imprime. El responsable debe restablecer MFA de la cuenta de desarrollo al terminar para que el usuario configure su propio autenticador. No ejecutar contra datos de producción.

`frontend/e2e/extension.mjs` (`npm --prefix frontend run test:extension`) repite la carga de extensión. No verifica reputación externa, Gmail real, despliegue de Vercel ni interacción de permisos opcionales concedidos por el usuario.

Se ejecutaron ocho pruebas de Vitest sobre el límite de sesión de la API y los formularios de consentimiento/errores. Pasaron las ocho con Vitest 5.0.5. `npm --prefix frontend run build` pasó con TypeScript estricto y Vite 6.4.4. La auditoría npm posterior a la actualización informa cero vulnerabilidades; su salida está en `docs/evidence/frontend-audit.json`.

Capturas: `docs/evidence/dashboard.png`, `dashboard-mobile.png` y `extension.png`. Documentos descargados de prueba (posteriormente regenerados con una cuenta desechable para QA visual): `docs/evidence/sample-report.pdf`, `.docx` y `.xlsx`. Su contenido muestra datos académicos controlados y puede incluir registros de múltiples repeticiones de la prueba. La verificación de firma no reemplaza la revisión visual de los documentos.

El recorrido completo web y la carga MV3 se repitieron satisfactoriamente tras las correcciones finales de reanálisis, validación Unicode, tipografías PDF, notas extensas y conteo de gráficas consolidadas del backend. El resultado final está en `docs/evidence/frontend-e2e-final.txt`; se regeneraron las capturas y las tres muestras descargadas. Las estadísticas de pruebas unitarias se mantienen en ocho pruebas aprobadas.
