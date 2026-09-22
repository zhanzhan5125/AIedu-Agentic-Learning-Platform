"""Add multi-agent learning, resource and messaging domains.

Revision ID: 20260921_0005
Revises: 20260920_0004
"""
from alembic import op
import sqlalchemy as sa

from app.db import Base
from app import models  # noqa: F401

revision = "20260921_0005"
down_revision = "20260920_0004"
branch_labels = None
depends_on = None


NEW_TABLES = [
    "consumer_inbox", "scheduled_notifications", "communication_messages",
    "communication_members", "communication_threads", "course_resources",
    "answer_analyses", "class_mastery_snapshots", "student_mastery_profiles",
    "learning_evidence", "agent_run_steps", "agent_runs",
    "question_knowledge_points", "knowledge_points",
]


def upgrade() -> None:
    # Metadata creation is intentionally used for this isolated v2 schema, matching
    # the project's baseline migration and keeping SQLite/MySQL definitions aligned.
    Base.metadata.create_all(bind=op.get_bind())
    inspector = sa.inspect(op.get_bind())
    ai_columns = {column["name"] for column in inspector.get_columns("ai_jobs")}
    if "agent_run_id" not in ai_columns:
        with op.batch_alter_table("ai_jobs") as batch:
            batch.add_column(sa.Column("agent_run_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_ai_job_agent_run", "agent_runs", ["agent_run_id"], ["id"], ondelete="SET NULL")
    chat_columns = {column["name"] for column in inspector.get_columns("chat_messages")}
    missing = {
        "knowledge_point_ids": sa.Column("knowledge_point_ids", sa.JSON(), nullable=True),
        "policy_mode": sa.Column("policy_mode", sa.String(length=32), nullable=True),
        "matched_assignment_id": sa.Column("matched_assignment_id", sa.Integer(), nullable=True),
        "similarity": sa.Column("similarity", sa.Integer(), nullable=True),
        "hint_level": sa.Column("hint_level", sa.Integer(), nullable=True),
    }
    if set(missing) - chat_columns:
        with op.batch_alter_table("chat_messages") as batch:
            for name, column in missing.items():
                if name not in chat_columns:
                    batch.add_column(column)
            if "matched_assignment_id" not in chat_columns:
                batch.create_foreign_key("fk_chat_message_assignment", "assignments", ["matched_assignment_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch:
        batch.drop_constraint("fk_chat_message_assignment", type_="foreignkey")
        for name in ("hint_level", "similarity", "matched_assignment_id", "policy_mode", "knowledge_point_ids"):
            batch.drop_column(name)
    with op.batch_alter_table("ai_jobs") as batch:
        batch.drop_constraint("fk_ai_job_agent_run", type_="foreignkey")
        batch.drop_column("agent_run_id")
    for table in NEW_TABLES:
        op.drop_table(table)
