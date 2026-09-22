"""Store course-resource embedding metadata.

Revision ID: 20260921_0009
Revises: 20260921_0008
"""
from alembic import op
import sqlalchemy as sa


revision = "20260921_0009"
down_revision = "20260921_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("course_resources")}
    with op.batch_alter_table("course_resources") as batch_op:
        if "chunk_count" not in columns:
            batch_op.add_column(sa.Column("chunk_count", sa.Integer(), nullable=True))
        if "embedding_model" not in columns:
            batch_op.add_column(sa.Column("embedding_model", sa.String(length=100), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("course_resources")}
    with op.batch_alter_table("course_resources") as batch_op:
        if "embedding_model" in columns:
            batch_op.drop_column("embedding_model")
        if "chunk_count" in columns:
            batch_op.drop_column("chunk_count")
