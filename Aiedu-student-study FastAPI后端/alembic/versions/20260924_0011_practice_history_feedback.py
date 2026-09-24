"""Add persisted practice answers and automatic feedback.

Revision ID: 20260924_0011
Revises: 20260922_0010
"""
from alembic import op
import sqlalchemy as sa


revision = "20260924_0011"
down_revision = "20260922_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("practice_sessions")}
    additions = (
        ("answers", sa.Column("answers", sa.JSON(), nullable=True)),
        ("feedback", sa.Column("feedback", sa.JSON(), nullable=True)),
        ("score", sa.Column("score", sa.Integer(), nullable=True)),
        ("total_score", sa.Column("total_score", sa.Integer(), nullable=True)),
        ("completed_at", sa.Column("completed_at", sa.DateTime(), nullable=True)),
    )
    for name, column in additions:
        if name not in columns:
            op.add_column("practice_sessions", column)


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("practice_sessions")}
    for name in ("completed_at", "total_score", "score", "feedback", "answers"):
        if name in columns:
            op.drop_column("practice_sessions", name)
