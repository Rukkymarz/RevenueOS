"""Force row-level isolation for business-owned records.

Migration must run as a privileged schema owner. API must connect as revenueos_app.
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "leads", "contacts", "clients", "opportunities", "tasks", "campaigns", "proposals",
    "websites", "media_jobs", "approvals", "message_drafts", "audit_events",
    "integration_events", "knowledge", "workflows", "agent_memory", "ai_runs",
)


def upgrade():
    # No tenant setting means no access, including if a developer forgets a WHERE filter.
    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'''CREATE POLICY tenant_isolation ON "{table}"
                 FOR ALL TO revenueos_app
                 USING (business_id = NULLIF(current_setting('app.business_id', true), ''))
                 WITH CHECK (business_id = NULLIF(current_setting('app.business_id', true), ''))''')
    op.execute("GRANT USAGE ON SCHEMA public TO revenueos_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO revenueos_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO revenueos_app")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO revenueos_app")


def downgrade():
    for table in TENANT_TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
