"""Associate system notifications with a teaching offering.

Revision ID: 20260921_0008
Revises: 20260921_0007
"""
from alembic import op
import sqlalchemy as sa


revision = "20260921_0008"
down_revision = "20260921_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("notifications")}
    # A fresh database is created from current metadata by the baseline migration,
    # so the column may already exist when the remaining revisions are replayed.
    if "offering_id" not in columns:
        with op.batch_alter_table("notifications") as batch_op:
            batch_op.add_column(sa.Column("offering_id", sa.Integer(), nullable=True))
            batch_op.create_index("ix_notifications_offering_id", ["offering_id"])
            batch_op.create_foreign_key(
                "fk_notifications_offering_id_course_offerings",
                "course_offerings",
                ["offering_id"],
                ["id"],
                ondelete="CASCADE",
            )


def downgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_constraint(
            "fk_notifications_offering_id_course_offerings",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_notifications_offering_id")
        batch_op.drop_column("offering_id")
