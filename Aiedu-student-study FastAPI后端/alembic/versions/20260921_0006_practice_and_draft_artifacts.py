"""Persist AI assignment drafts and personal practice sessions.

Revision ID: 20260921_0006
Revises: 20260921_0005
"""
from alembic import op
import sqlalchemy as sa

from app.db import Base
from app import models  # noqa: F401

revision = "20260921_0006"
down_revision = "20260921_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("assignments")}
    if "origin" not in columns:
        op.add_column("assignments", sa.Column("origin", sa.String(length=32), nullable=False,
                                               server_default="manual"))
    if "agent_run_id" not in columns:
        with op.batch_alter_table("assignments") as batch:
            batch.add_column(sa.Column("agent_run_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_assignment_agent_run", "agent_runs", ["agent_run_id"], ["id"],
                                     ondelete="SET NULL")


def downgrade() -> None:
    op.drop_table("practice_sessions")
    with op.batch_alter_table("assignments") as batch:
        batch.drop_constraint("fk_assignment_agent_run", type_="foreignkey")
        batch.drop_column("agent_run_id")
        batch.drop_column("origin")
