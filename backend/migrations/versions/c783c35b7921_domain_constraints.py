"""Validate domain invariants at the persistence boundary."""
from alembic import op

revision = "c783c35b7921"
down_revision = "b325e8848210"
branch_labels = None
depends_on = None

CONSTRAINTS = {
    "users": [("ck_users_role", "role IN ('admin','analyst','user')"), ("ck_users_mfa_secret", "mfa_enabled = false OR mfa_secret_encrypted IS NOT NULL")],
    "evaluations": [("ck_evaluations_score", "score >= 0 AND score <= 100"), ("ck_evaluations_risk", "risk IN ('low','moderate','high','critical')"), ("ck_evaluations_status", "status IN ('preliminary','complete','pending','inconclusive')"), ("ck_evaluations_source", "source IN ('manual','extension','email','sms','api')")],
    "alerts": [("ck_alerts_risk", "risk IN ('low','moderate','high','critical')")],
    "incidents": [("ck_incidents_severity", "severity IN ('low','moderate','high','critical')"), ("ck_incidents_status", "status IN ('open','investigating','resolved','dismissed')")],
    "reports": [("ck_reports_kind", "kind IN ('evaluations','alerts','incidents','consolidated')"), ("ck_reports_format", "format IN ('pdf','docx','xlsx')"), ("ck_reports_status", "status IN ('pending','complete','failed')"), ("ck_reports_scope", "scope IN ('own','organization')")],
    "jobs": [("ck_jobs_kind", "kind IN ('evaluation','report','email','webhook')"), ("ck_jobs_status", "status IN ('pending','running','complete','failed')"), ("ck_jobs_attempts", "attempts >= 0")],
    "policies": [("ck_policies_retention", "retention_days >= 1 AND retention_days <= 3650"), ("ck_policies_singleton", "id = 1")],
    "privacy_requests": [("ck_privacy_kind", "kind IN ('access','rectification','cancellation','opposition')"), ("ck_privacy_status", "status IN ('pending','processing','completed','rejected')")],
    "rate_limits": [("ck_rate_limits_count", "count >= 0")],
    "provider_budgets": [("ck_provider_budgets_counts", "calls >= 0 AND tokens >= 0")],
}


def upgrade():
    for table, constraints in CONSTRAINTS.items():
        with op.batch_alter_table(table) as batch:
            for name, condition in constraints:
                batch.create_check_constraint(name, condition)


def downgrade():
    for table, constraints in reversed(list(CONSTRAINTS.items())):
        with op.batch_alter_table(table) as batch:
            for name, _ in constraints:
                batch.drop_constraint(name, type_="check")
