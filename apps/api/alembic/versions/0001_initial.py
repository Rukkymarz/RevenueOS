"""Initialize core business tables and pgvector knowledge memory.

Revision ID: 0001
Revises:
"""
from alembic import op
from revenueos.db import Base
from revenueos import models  # noqa: F401

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    op.execute("ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS embedding vector(1536)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_business_created ON knowledge (business_id, created_at)")
    # Tenant-scoped RLS is a defense-in-depth layer; API also checks every membership and object.
    # Application connects with a non-BYPASSRLS role, session business ID set per transaction if enabled.
    # RLS policy deployment is documented separately because migrations running as table owner bypass it.


def downgrade():
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
