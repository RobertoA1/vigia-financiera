# Vigía Financiera — Identidad propuesta

Estado: propuesta implementada, pendiente de validación visual por el autor del proyecto.

**VIGÍA.** expresa observación previa a la acción y un criterio humano informado por evidencia. El símbolo de escudo y las órbitas de radar representan protección y visibilidad. El punto de acento actúa como señal de observación. No utiliza marcas ni activos de Splunk ni de las entidades financieras priorizadas.

La interfaz toma como referencia el patrón de una consola SOC: navegación lateral persistente, resumen de actividad, cola de analista densa, clasificación visible y detalle de evidencia. Presenta todos los estados vacíos y los errores sin inventar actividad.

| Elemento | Valor inicial | Uso |
| --- | --- | --- |
| Fondo | `#101518` | Espacio de trabajo |
| Paneles | `#181f23` | Agrupación de evidencia |
| Texto principal | `#e5eaec` | Lectura |
| Texto secundario | `#929fa7` | Contexto |
| Acento de marca | `#2bd8ae` | Acción primaria, navegación, observación |
| Verde suave | `#b8ed83` | Señales auxiliares |
| Ámbar | `#e6b567` | Atención |
| Rojo suave | `#f78486` | Riesgo crítico |

La marca usa Space Grotesk; la interfaz usa DM Sans. Ambas tipografías se distribuyen dentro de la aplicación, con sus licencias en `frontend/public/licenses/`, con alternativas del sistema y sin llamadas a servicios externos de fuentes. Los iconos pertenecen a Lucide. Los niveles de riesgo incluyen etiquetas de texto para que el color no sea la única señal.

La configuración pública de compilación permite cambiar nombre, nombre corto, organización, acento y frecuencia de actualización mediante `VITE_APP_NAME`, `VITE_APP_SHORT_NAME`, `VITE_ORGANIZATION`, `VITE_ACCENT_COLOR` y `VITE_POLL_INTERVAL_MS`. El archivo `.env` de la raíz alimenta Vite localmente; Docker recibe los mismos valores como argumentos de compilación. Las variables `VITE_*` son públicas y nunca deben contener secretos. El operador debe mantener contraste suficiente al cambiar el color.

Las capturas verificadas con Chromium están en [evidence/dashboard.png](evidence/dashboard.png) y [evidence/dashboard-mobile.png](evidence/dashboard-mobile.png). Se actualizan después de probar contra la API real; los enlaces de demostración usan `.invalid` y no se visitan.
