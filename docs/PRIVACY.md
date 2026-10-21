# Privacidad y protección de datos

Marco de referencia consultado: [Ley 29733](https://www.gob.pe/institucion/congreso-de-la-republica/normas-legales/243470-29733) y su [Reglamento DS 016-2024-JUS](https://www.gob.pe/institucion/anpd/normas-legales/6554453-n-016-2024-jus). La ANPD señala que el nuevo reglamento [entró en vigor el 31 de marzo de 2025](https://www.gob.pe/institucion/anpd/campa%C3%B1as/128319-nuevo-reglamento-de-proteccion-de-datos-personales). Las medidas siguientes son decisiones de diseño del prototipo, no una certificación de cumplimiento legal.

## Finalidad y datos tratados

La finalidad es estudiar indicadores de phishing financiero y administrar sus evaluaciones, alertas e incidentes. Se guardan identidad de cuenta, contraseña hasheada, estado de MFA, sesiones, zona horaria, preferencias, dominio evaluado, evidencia de riesgo, acciones y reportes autorizados. La semilla TOTP y los códigos de recuperación se protegen mediante cifrado/hash respectivamente. Observaciones de solicitudes ARCO y payloads de correo que requieren datos personales se cifran con la clave de campo del entorno.

La URL completa se procesa transitoriamente. Se elimina su ruta, query y fragmento antes de persistirla; el display solo conserva origen y un marcador si había ruta. El texto pegado de correo/SMS no se guarda. La extensión transmite solamente el origen y no accede a contenido de formularios. No se recopilan credenciales bancarias, tarjetas ni OTP de entidades financieras. Un dominio también puede contener datos identificables: el acceso, los plazos y la difusión de estas evidencias deben limitarse.

## Información y consentimiento

El usuario puede consultar la vista Privacidad antes de usar integraciones. La consulta externa requiere una casilla expresa por evaluación, inicialmente desmarcada. También requiere que el administrador configure y habilite al proveedor. VirusTotal recibe un dominio para consultar reputación; OpenAI recibe evidencia estructurada minimizada y antecedentes agregados, sin mensaje original ni identificadores de cuenta. No hay navegación autónoma del sitio analizado. Un servicio deshabilitado no se presenta como si hubiera ejecutado una revisión.

El análisis automático de navegación es opcional, requiere permiso adicional y activación explícita. Puede desactivarse desde el popup y revocarse en el navegador. No se activa al instalar ni se presenta como lectura universal de la actividad del dispositivo. Las preferencias de notificación están separadas del consentimiento de proveedores.

## Derechos y conservación

La interfaz permite exportación propia y solicitudes de acceso, rectificación, cancelación u oposición. El backend limita el acceso al titular; el administrador puede consultar la petición, documentar respuesta y procesarla. Una cancelación completada con eliminación expresa revoca sesiones, desactiva y desidentifica la cuenta, elimina evaluaciones y artefactos relacionados y conserva auditoría mínima. El control requiere revisar previamente la identidad y el alcance de la solicitud. No se envían respuestas a direcciones arbitrarias proporcionadas por un webhook.

`RETENTION_DAYS=90` es una propuesta inicial de minimización, no un plazo exigido por la ley. Es configurable. El worker purga periódicamente evaluaciones antiguas, artefactos, sesiones/caché expiradas y datos operacionales que agotaron su retención; solicitudes ARCO no resueltas no se eliminan por vencimiento del plazo general. Los respaldos tienen su propio calendario: el operador debe excluir de restauraciones rutinarias datos cuya cancelación ya fue aprobada, conservando un registro mínimo de supresión.

## Responsabilidad de operación

Antes de usar datos reales, el responsable del proyecto debe identificar al responsable/encargados del tratamiento, comunicar finalidades y canales de atención, determinar obligaciones de registro aplicables y evaluar los proveedores, ubicación de almacenamiento y posibles flujos transfronterizos. Los mecanismos técnicos no sustituyen esa definición institucional ni la revisión del alcance legal para el despliegue concreto.

El MVP es de una sola organización; no ofrece aislamiento entre organizaciones distintas. MFA administrativo, RBAC, auditoría y sesiones revocables protegen el acceso, pero el operador del servidor y los administradores de base de datos siguen siendo personal privilegiado. Secretos y backups no deben almacenarse en un repositorio público. Los editores n8n/Langflow requieren acceso administrativo restringido. Las brechas deben gestionarse conforme al procedimiento institucional y las obligaciones aplicables del reglamento vigente; la aplicación no presenta una detección de URL sospechosa como prueba de una brecha de datos personales.
