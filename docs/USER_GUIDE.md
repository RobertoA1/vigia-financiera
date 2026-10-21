# Manual de usuario

## Acceder y proteger la cuenta

Un administrador crea tu cuenta de Vigía y te facilita la contraseña inicial por un canal privado. Inicia sesión y cámbiala en Mi cuenta. Administradores y analistas deben configurar un autenticador TOTP antes de acceder a evaluaciones. Escanea el QR o introduce la clave manualmente en tu autenticador y confirma el código de seis dígitos. Guarda los códigos de recuperación fuera de la aplicación: cada uno funciona una sola vez. Los OTP de tu banco nunca se solicitan en Vigía.

La zona horaria se toma de tu navegador durante el primer acceso y se guarda en tu perfil. Puedes modificarla con un nombre IANA, por ejemplo America/Lima. Cambiarla no modifica las fechas UTC almacenadas.

## Analizar enlaces

En Analizar enlace pega una URL HTTP o HTTPS. Si no tiene esquema, el motor interpreta HTTPS. La casilla de proveedores externos es opcional: permite enviar el dominio a VirusTotal y evidencia estructurada a OpenAI, si el administrador habilitó esos servicios. Sin ella, el análisis es local y puede figurar como no concluyente por falta de evidencia externa.

En Correo o mensaje pega un texto autorizado. Se extraen hasta diez enlaces por lote; el texto solo se procesa en memoria y se limpia del formulario tras el análisis. Esta función no conecta con tu buzón ni lee SMS automáticamente. No pegues contraseñas, códigos OTP, números de tarjeta ni información privada de terceros.

La evaluación muestra puntuación 0–100, nivel, estado, indicadores, fuentes y recomendaciones. Riesgo bajo no garantiza legitimidad. Una evaluación preliminar puede cambiar cuando llega evidencia externa. Los destinos se presentan como texto no navegable; la plataforma no necesita abrirlos para analizar sus indicadores.

## Interpretar y actuar

| Nivel inicial | Puntos | Acción práctica |
|---|---|---|
| Bajo | 0–24 | Revisar origen; ausencia de señales no acredita seguridad |
| Moderado | 25–49 | Verificar el dominio y evitar acciones sensibles sin confirmación |
| Alto | 50–74 | Evitar continuar o introducir datos y consultar un canal oficial |
| Crítico | 75–100 | Suspender interacción y solicitar revisión del incidente |

La aplicación no afirma que hubo un hackeo. Si ya compartiste datos con un sitio sospechoso, contacta a tu entidad mediante su aplicación, número o sitio oficial conocido, sin reutilizar el enlace recibido.

## Consultar historial, alertas y reportes

Evaluaciones permite filtrar por dominio, nivel y estado y abrir el detalle. Los usuarios finales solo acceden a sus registros; analistas y administradores tienen alcance de la organización. El dashboard resume esos mismos permisos. No se muestra un mapa inventado si no hay geografía verificada.

En Alertas puedes marcar avisos como leídos. Las notificaciones de navegador son opcionales y funcionan mientras la aplicación está abierta y el permiso esté concedido. La extensión tiene su propio permiso de notificación. Los avisos por correo dependen de tus preferencias y del servidor configurado por el administrador.

En Reportes selecciona tipo, formato y período. El worker procesa la solicitud; cuando se completa aparece la descarga. PDF facilita lectura/impresión, DOCX puede editarse y XLSX incluye filtro y gráfico. Un reporte fallido no se presenta como completo: reduce el período o solicita ayuda al administrador.

## Gestión para analistas

Abre Incidentes para revisar severidad, estado, responsable y antecedentes. Puedes asignar un analista activo, registrar observaciones y pasar a En investigación, Resuelto o Descartado según la evidencia. Cada acción agrega un evento a la timeline. La IA propone resúmenes y escalamiento; no reemplaza la decisión humana ni cambia el score.

## Privacidad y recuperación

En Privacidad puedes descargar tus datos y presentar solicitudes de acceso, rectificación, cancelación u oposición. El administrador revisa y documenta su respuesta. Cancelar una cuenta no equivale a desactivar avisos: la eliminación de registros es una acción explícita que el administrador debe verificar.

La recuperación de contraseña envía un enlace al correo registrado si el entorno tiene SMTP operativo. La respuesta pública es deliberadamente genérica para no revelar cuentas. Recuperar la contraseña conserva MFA; usa un código de recuperación si perdiste tu autenticador. Si no tienes ninguno, contacta al administrador y verifica tu identidad por un canal autorizado.
