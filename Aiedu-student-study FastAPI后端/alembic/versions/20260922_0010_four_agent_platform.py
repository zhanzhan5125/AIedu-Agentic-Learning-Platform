"""Add the bounded four-agent platform data model.

Revision ID: 20260922_0010
Revises: 20260921_0009
"""
from alembic import op
import sqlalchemy as sa


revision = "20260922_0010"
down_revision = "20260921_0009"
branch_labels = None
depends_on = None


def _columns(inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    agent_columns = _columns(inspector, "agent_runs")
    with op.batch_alter_table("agent_runs") as batch:
        if "agent_name" not in agent_columns:
            batch.add_column(sa.Column("agent_name", sa.String(64), nullable=True))
        if "task_type" not in agent_columns:
            batch.add_column(sa.Column("task_type", sa.String(64), nullable=True))
        if "parent_run_id" not in agent_columns:
            batch.add_column(sa.Column("parent_run_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_agent_run_parent", "agent_runs", ["parent_run_id"], ["id"], ondelete="SET NULL")
            batch.create_index("ix_agent_runs_parent_run_id", ["parent_run_id"])
        if "plan" not in agent_columns:
            batch.add_column(sa.Column("plan", sa.JSON(), nullable=True))
        if "reflection_count" not in agent_columns:
            batch.add_column(sa.Column("reflection_count", sa.Integer(), nullable=False, server_default="0"))
        batch.create_index("ix_agent_runs_agent_name", ["agent_name"])
        batch.create_index("ix_agent_runs_task_type", ["task_type"])

    step_columns = _columns(inspector, "agent_run_steps")
    with op.batch_alter_table("agent_run_steps") as batch:
        if "agent_name" not in step_columns:
            batch.add_column(sa.Column("agent_name", sa.String(64), nullable=True))
        if "step_type" not in step_columns:
            batch.add_column(sa.Column("step_type", sa.String(32), nullable=True))

    resource_columns = _columns(inspector, "course_resources")
    with op.batch_alter_table("course_resources") as batch:
        if "resource_type" not in resource_columns:
            batch.add_column(sa.Column("resource_type", sa.String(32), nullable=False,
                                       server_default="courseware"))

    op.create_table(
        "resource_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("resource_id", sa.Integer(), sa.ForeignKey("course_resources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("offering_id", sa.Integer(), sa.ForeignKey("course_offerings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.String(32), nullable=False, server_default="paragraph"),
        sa.Column("heading_path", sa.String(500)),
        sa.Column("page_number", sa.Integer()),
        sa.Column("slide_number", sa.Integer()),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("resource_id", "position", name="uq_resource_chunk_position"),
    )
    op.create_index("ix_resource_chunks_offering_resource", "resource_chunks", ["offering_id", "resource_id"])
    op.create_index("ix_resource_chunks_resource_id", "resource_chunks", ["resource_id"])
    op.create_index("ix_resource_chunks_offering_id", "resource_chunks", ["offering_id"])
    op.create_index("ix_resource_chunks_content_hash", "resource_chunks", ["content_hash"])

    op.create_table(
        "course_map_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("app_courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("offering_id", sa.Integer(), sa.ForeignKey("course_offerings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("title", sa.String(200), nullable=False, server_default="课程知识路线"),
        sa.Column("summary", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("app_users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="SET NULL")),
        sa.Column("published_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("course_id", "version", name="uq_course_map_version"),
    )
    op.create_index("ix_course_map_course_status", "course_map_versions", ["course_id", "status"])
    op.create_index("ix_course_map_versions_course_id", "course_map_versions", ["course_id"])
    op.create_index("ix_course_map_versions_offering_id", "course_map_versions", ["offering_id"])

    op.create_table(
        "course_map_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("course_map_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("knowledge_point_id", sa.Integer(), sa.ForeignKey("knowledge_points.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("version_id", "node_key", name="uq_course_map_node_key"),
    )
    op.create_index("ix_course_map_nodes_version_id", "course_map_nodes", ["version_id"])

    op.create_table(
        "course_map_edges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("course_map_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_node_id", sa.Integer(), sa.ForeignKey("course_map_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_node_id", sa.Integer(), sa.ForeignKey("course_map_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(24), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("version_id", "source_node_id", "target_node_id", "relation_type", name="uq_course_map_edge"),
    )
    op.create_index("ix_course_map_edges_version_id", "course_map_edges", ["version_id"])

    op.create_table(
        "course_map_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("node_id", sa.Integer(), sa.ForeignKey("course_map_nodes.id", ondelete="CASCADE")),
        sa.Column("edge_id", sa.Integer(), sa.ForeignKey("course_map_edges.id", ondelete="CASCADE")),
        sa.Column("chunk_id", sa.Integer(), sa.ForeignKey("resource_chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_course_map_evidence_target", "course_map_evidence", ["node_id", "edge_id"])
    op.create_index("ix_course_map_evidence_chunk_id", "course_map_evidence", ["chunk_id"])

    op.create_table(
        "agent_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("app_users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("feedback_type", sa.String(24), nullable=False),
        sa.Column("before_value", sa.JSON()),
        sa.Column("after_value", sa.JSON()),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_feedback_run", "agent_feedback", ["run_id", "created_at"])


def downgrade() -> None:
    op.drop_table("agent_feedback")
    op.drop_table("course_map_evidence")
    op.drop_table("course_map_edges")
    op.drop_table("course_map_nodes")
    op.drop_table("course_map_versions")
    op.drop_table("resource_chunks")
    with op.batch_alter_table("course_resources") as batch:
        batch.drop_column("resource_type")
    with op.batch_alter_table("agent_run_steps") as batch:
        batch.drop_column("step_type")
        batch.drop_column("agent_name")
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_column("reflection_count")
        batch.drop_column("plan")
        batch.drop_column("parent_run_id")
        batch.drop_column("task_type")
        batch.drop_column("agent_name")
