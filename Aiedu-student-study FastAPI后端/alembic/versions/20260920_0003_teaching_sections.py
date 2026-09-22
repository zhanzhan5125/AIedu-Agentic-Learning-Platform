"""Add teaching-section identity to course offerings.

Revision ID: 20260920_0003
Revises: 20260920_0002
"""
import sqlalchemy as sa
from alembic import op

revision = "20260920_0003"
down_revision = "20260920_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MySQL DDL is non-transactional. The guards also make a retry safe if a
    # previous migration attempt stopped after adding one of the columns.
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("course_offerings")}
    if "section_code" not in columns:
        op.add_column(
            "course_offerings",
            sa.Column("section_code", sa.String(length=32), nullable=False, server_default="01"),
        )
    if "section_name" not in columns:
        op.add_column(
            "course_offerings",
            sa.Column("section_name", sa.String(length=100), nullable=True),
        )
    offerings = sa.table("course_offerings", sa.column("section_code", sa.String()),
                         sa.column("section_name", sa.String()))
    op.execute(offerings.update().where(offerings.c.section_name.is_(None)).values(
        section_name=sa.literal("教学班") + offerings.c.section_code
    ))
    inspector = sa.inspect(op.get_bind())
    unique_names = {item["name"] for item in inspector.get_unique_constraints("course_offerings")}
    # Create the replacement first: its leading course_id also supports the
    # course foreign key, allowing MySQL to drop the old composite index.
    if "uq_offering_course_term_section" not in unique_names:
        op.create_unique_constraint(
            "uq_offering_course_term_section",
            "course_offerings",
            ["course_id", "year", "term", "section_code"],
        )
    if "uq_offering" in unique_names:
        op.drop_constraint("uq_offering", "course_offerings", type_="unique")
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("course_offerings", "section_code", server_default=None)


def downgrade() -> None:
    # This will intentionally fail if multiple sections now exist for the same
    # teacher/course/term; such data must be merged explicitly before rollback.
    op.create_unique_constraint(
        "uq_offering",
        "course_offerings",
        ["course_id", "teacher_id", "year", "term"],
    )
    op.drop_constraint("uq_offering_course_term_section", "course_offerings", type_="unique")
    op.drop_column("course_offerings", "section_name")
    op.drop_column("course_offerings", "section_code")
