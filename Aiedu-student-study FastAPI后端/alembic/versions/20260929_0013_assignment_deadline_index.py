"""Index assignments for deadline recovery scans.

Revision ID: 20260929_0013
Revises: 20260929_0012
"""
from alembic import op
import sqlalchemy as sa


revision = "20260929_0013"
down_revision = "20260929_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes("assignments")}
    if "ix_assignments_status_end_at" not in indexes:
        op.create_index("ix_assignments_status_end_at", "assignments", ["status", "end_at"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes("assignments")}
    if "ix_assignments_status_end_at" in indexes:
        op.drop_index("ix_assignments_status_end_at", table_name="assignments")
