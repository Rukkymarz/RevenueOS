"""Bind approvals to reviewed content.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

def upgrade():
    # Initial installs use the current metadata in 0001, which can already
    # contain this column. Older installations still need the additive upgrade.
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("approvals")}
    if "review_hash" not in columns:
        op.add_column("approvals", sa.Column("review_hash", sa.String(length=64), nullable=True))

def downgrade():
    op.drop_column("approvals", "review_hash")
