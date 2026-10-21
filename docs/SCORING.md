# Motor y puntuación de riesgo

Versión `vigia-heuristic-1.0.0`. El motor analiza sintaxis/contexto de una URL; no descarga contenido, sigue redirecciones, hace capturas ni resuelve el DNS del destino. `tldextract` usa una copia local de la Public Suffix List sin actualizaciones HTTP durante el análisis. `idna` normaliza nombres internacionales y `rapidfuzz` compara similitudes. La existencia de un dominio oficial no garantiza que todo su contenido esté libre de compromiso.

## Reglas iniciales

| Grupo | Indicador | Peso |
|---|---|---|
| identity | Referencia a BCP/viabcp, Interbank o BBVA fuera de dominios oficiales | 50 |
| identity | Similitud aproximada de alias de al menos cuatro caracteres, ratio ≥78 | 40 |
| structure | Mezcla de alfabetos latino/cirílico/griego | 20 |
| structure | Host IP público | 20 |
| structure | Dominio largo, profundidad >5 etiquetas o etiqueta >35 caracteres | 15 |
| structure | IDN/punycode, ≥3 guiones o URL >500 caracteres | 10 cada señal, no acumulables entre sí |
| context | Palabras de acceso/verificación fuera del catálogo financiero | 15 |
| context | Parámetros conocidos de redirección | 10 |
| transport | HTTP sin TLS | 10 |
| transport | Puerto distinto de 80/443 | 5 |

Por cada grupo se conserva **el mayor peso**; se suman los máximos de grupos distintos y se limita a 100. Esto evita sumar señales redundantes de longitud, guiones, múltiples marcas o alfabetos como si fueran pruebas independientes. Ningún indicador aislado de HTTPS/IDN demuestra fraude. Los homógrafos solo se cubren mediante normalización y un conjunto acotado de equivalencias: no se declara implementación completa de Unicode UTS39.

Catálogo inicial verificado en las webs oficiales: BCP `viabcp.com`, Interbank `interbank.pe`, BBVA `bbva.pe`. Las coincidencias oficiales requieren igualdad o sufijo con punto; `viabcp.com.atacante.invalid` no coincide. Los dominios históricos/alternativos no se presumen oficiales. `BANK_DOMAINS_JSON` permite ajustar el catálogo bajo revisión; cambiarlo requiere reiniciar API/worker. Los umbrales bajo/moderado/alto/crítico son configurables y deben conservar orden estricto.

La heurística se aplica antes de borrar rutas/parámetros, pero esas partes no sobreviven en la evidencia. No se guardan valores de query ni path. El display contiene el origen y, si existía una ruta, el marcador `[ruta omitida]`. La extensión es aún más restrictiva: envía solo el origen, por lo que no dispone de señales del path/query.

## Reputación

Se consulta exclusivamente un informe GET de dominio en el host fijo `www.virustotal.com`; no se envía una URL completa ni se solicita un escaneo. La puntuación final es el máximo entre heurística y un piso reputacional: ≥3 motores maliciosos→85, ≥1 malicioso→60, ≥2 sospechosos→35. No se suman los resultados de distintos motores como eventos independientes. Son pesos iniciales explicables, no probabilidades calibradas.

No encontrarse un informe es `not_found`, un límite es `rate_limited`, fallo/configuración ausente es `unavailable`; esos resultados no reducen el score ni acreditan legitimidad. Un informe con cero detecciones conserva la puntuación heurística y advierte que no garantiza seguridad. Las fechas `checked_at` y `evidence_at` distinguen consulta y antigüedad de evidencia. La caché tiene TTL configurable de21 600 segundos por defecto.

No se reintenta inmediatamente un fallo de VirusTotal público para respetar su cuota. El operador puede reanalizar después del intervalo; los trabajos operacionales usan reintentos persistentes y backoff para fallos de ejecución, SMTP y webhooks. La cola no tiene una copia de la URL original. El presupuesto se reserva en PostgreSQL con lock antes de consultar. La caché no obliga a esperar una consulta externa para responder a la navegación: se devuelve primero la heurística.

## IA y límites

La IA recibe códigos/títulos de indicadores, score/risk, dominio, contadores reputacionales y antecedentes agregados bajo RBAC. No recibe mensajes, credenciales, URLs originales ni identificadores de usuarios. Solo recomienda y explica; no modifica score. Los errores, rechazos de esquema y falta de presupuesto son visibles. Una explicación en lenguaje natural no transforma evidencia débil en confirmación de phishing.

El benchmark UCI usa un corpus histórico global con marcas y patrones distintos del foco peruano. En la muestra estratificada de 2000 URLs a umbral 50, la versión inicial detectó 1/1000 muestras etiquetadas como phishing y produjo 0/1000 falsos positivos: **recall 0.1% y falsos negativos 99.9%**. No se oculta este resultado ni se ajustan umbrales sobre la muestra para aparentar eficacia. La implementación es útil para estudiar integración y señales concretas de suplantación, pero sus heurísticas locales no son una protección general autónoma. Debe ampliarse y validarse con corpus representativo, reputación actual y revisión humana antes de cualquier piloto real. Las cifras exactas y latencias están en `evidence/dataset-benchmark.json`.
