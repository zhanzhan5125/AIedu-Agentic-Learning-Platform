"""Add explicit AI/manual grading workflow fields.

Revision ID: 20260920_0002
Revises: 20260919_0001
"""
import sqlalchemy as sa
from alembic import op

revision = "20260920_0002"
down_revision = "20260919_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("submissions")}
    columns = [
        sa.Column("ai_graded_at", sa.DateTime(), nullable=True),
        sa.Column("graded_at", sa.DateTime(), nullable=True),
        sa.Column("grading_source", sa.String(length=32), nullable=True),
        sa.Column("review_reason", sa.String(length=500), nullable=True),
        sa.Column("ai_confidence", sa.Integer(), nullable=True),
    ]
    for column in columns:
        if column.name not in existing:
            op.add_column("submissions", column)


def downgrade() -> None:
    op.drop_column("submissions", "ai_confidence")
    op.drop_column("submissions", "review_reason")
    op.drop_column("submissions", "grading_source")
    op.drop_column("submissions", "graded_at")
    op.drop_column("submissions", "ai_graded_at")
