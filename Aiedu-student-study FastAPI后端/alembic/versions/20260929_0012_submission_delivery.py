"""Add submission versioning and outbox deduplication.

Revision ID: 20260929_0012
Revises: 20260924_0011
"""
from alembic import op
import sqlalchemy as sa


revision = "20260929_0012"
down_revision = "20260924_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    submission_columns = {column["name"] for column in inspector.get_columns("submissions")}
    if "version" not in submission_columns:
        op.add_column("submissions", sa.Column("version", sa.Integer(), nullable=False,
                                                server_default="0"))

    outbox_columns = {column["name"] for column in inspector.get_columns("outbox_events")}
    if "dedup_key" not in outbox_columns:
        with op.batch_alter_table("outbox_events") as batch_op:
            batch_op.add_column(sa.Column("dedup_key", sa.String(160), nullable=True))
            batch_op.create_unique_constraint("uq_outbox_dedup_key", ["dedup_key"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    outbox_columns = {column["name"] for column in inspector.get_columns("outbox_events")}
    if "dedup_key" in outbox_columns:
        with op.batch_alter_table("outbox_events") as batch_op:
            batch_op.drop_constraint("uq_outbox_dedup_key", type_="unique")
            batch_op.drop_column("dedup_key")
    submission_columns = {column["name"] for column in inspector.get_columns("submissions")}
    if "version" in submission_columns:
        op.drop_column("submissions", "version")
