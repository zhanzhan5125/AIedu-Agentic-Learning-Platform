"""Persist versioned assignment insight snapshots.

Revision ID: 20260921_0007
Revises: 20260921_0006
"""
from alembic import op

from app.db import Base
from app import models  # noqa: F401

revision = "20260921_0007"
down_revision = "20260921_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    op.drop_table("assignment_insight_snapshots")
