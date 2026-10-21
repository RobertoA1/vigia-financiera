"""Generate the data dictionary from SQLAlchemy metadata without connecting DB."""
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/"backend"))
from app.models import Base
from sqlalchemy import CheckConstraint

purpose={
    "users":"Identidad, rol fijo, preferencias, zona IANA, contraseña Argon2 y configuración MFA cifrada.",
    "sessions":"Sesiones revocables. Refresh hasheado, caducidad y estado de MFA; JWT refiere su id.",
    "recovery_tokens":"Recuperación de contraseña de un solo uso con hash y caducidad; no deshabilita MFA.",
    "evaluations":"Propietario, dominio minimizado y evidencia JSON versionada; sin URL cruda ni texto de mensajes.",
    "alerts":"Una alerta por evaluación; el riesgo y mensaje se actualizan con nueva evidencia.",
    "incidents":"Un incidente por evaluación, responsable opcional, severidad y timeline de acciones.",
    "reports":"Artefactos autorizados. Contenido binario base64, filtros, estado y alcance own/organization persistido.",
    "jobs":"Cola/outbox durable. Reclamo con SKIP LOCKED, lease, intentos y backoff; correo pendiente cifrado.",
    "audit":"Eventos críticos con actor opcional; SET NULL permite desidentificación sin perder registro operativo.",
    "policies":"Política singleton de la única organización: conservación y canales de notificación.",
    "privacy_requests":"Solicitudes ARCO con mensaje cifrado y estado de atención.",
    "rate_limits":"Contadores compartidos con ventana/caducidad para resistir procesos concurrentes.",
    "reputation_cache":"Evidencia pública de dominio con TTL compartida entre workers.",
    "provider_budgets":"Reservas de llamadas/tokens por proveedor y día UTC; intervalo mínimo reputacional.",
    "webhook_events":"Recibos idempotentes por event_id/tipo, resultado mínimo y callbacks de notificación.",
}
lines=["# Diccionario de datos", "", "Generado desde los modelos finales. PostgreSQL utiliza timestamps con zona horaria; API conserva offset y reportes convierten explícitamente a UTC. Las claves de cifrado están fuera de la base. Organización única; no hay multi-tenancy. JSON conserva evidencia versionada y timelines; no reemplaza las claves de identidad y permisos.", ""]
for table in Base.metadata.sorted_tables:
    lines += [f"## {table.name}","",purpose.get(table.name,"Registro operacional."),"","| Campo | Tipo | Nulo | Clave y referencia |","|---|---|---|---|"]
    for column in table.columns:
        references=[]
        if column.primary_key:references.append("PK")
        if column.unique:references.append("Único")
        for fk in column.foreign_keys:references.append(f"FK {fk.target_fullname} ({fk.ondelete or 'RESTRICT'})")
        lines.append(f"| {column.name} | {column.type} | {'Sí' if column.nullable else 'No'} | {'; '.join(references) or '—'} |")
    indexes=[f"{i.name}: "+", ".join(c.name for c in i.columns) for i in table.indexes]
    if indexes:lines += ["","Índices: "+"; ".join(indexes)+"."]
    checks=[str(c.sqltext) for c in table.constraints if isinstance(c,CheckConstraint)]
    if checks:lines += ["","Restricciones: "+"; ".join("`"+c+"`" for c in checks)+"."]
    lines.append("")
(root/"docs/DATA_DICTIONARY.md").write_text("\n".join(lines))
print("Diccionario generado:",len(Base.metadata.tables),"tablas.")
