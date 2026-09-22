"""Create durable course conversations and messages.

Revision ID: 20260920_0004
Revises: 20260920_0003
"""
import sqlalchemy as sa
from alembic import op

revision = "20260920_0004"
down_revision = "20260920_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "conversations" not in tables:
        op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("offering_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False, server_default="新对话"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("active", "archived", name="conversationstatus"),
                  nullable=False, server_default="active"),
        sa.Column("last_message_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offering_id"], ["course_offerings.id"], ondelete="CASCADE"),
    )
        op.create_index(
            "ix_conversations_user_status_updated",
            "conversations",
            ["user_id", "status", "updated_at"],
        )

    if "chat_messages" not in tables:
        op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("role", sa.Enum("system", "user", "assistant", "tool", name="messagerole"),
                  nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("pending", "completed", "failed", "cancelled",
                                    name="messagestatus"), nullable=False,
                  server_default="pending"),
        sa.Column("ai_job_id", sa.Integer(), nullable=True),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_job_id"], ["ai_jobs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("conversation_id", "sequence_no", name="uq_chat_message_sequence"),
    )
        op.create_index(
            "ix_chat_messages_conversation_created",
            "chat_messages",
            ["conversation_id", "created_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_conversation_created", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_conversations_user_status_updated", table_name="conversations")
    op.drop_table("conversations")
