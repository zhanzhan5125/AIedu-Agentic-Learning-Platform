"""Add teaching-section columns and uniqueness to the legacy schedule table.

The migration is additive and idempotent. Existing offerings become teaching
section ``01`` and retain their original ``ss_id`` and enrollments.
"""
from __future__ import annotations

from sqlalchemy import inspect, text

from app.db import engine


def migrate() -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        columns = {column["name"] for column in inspector.get_columns("schedule_sheet")}
        if "ss_section_code" not in columns:
            connection.execute(text(
                "ALTER TABLE schedule_sheet ADD COLUMN ss_section_code VARCHAR(32) "
                "NOT NULL DEFAULT '01' COMMENT '教学班编号' AFTER ss_status"
            ))
        if "ss_section_name" not in columns:
            connection.execute(text(
                "ALTER TABLE schedule_sheet ADD COLUMN ss_section_name VARCHAR(100) "
                "NULL COMMENT '教学班名称' AFTER ss_section_code"
            ))

        connection.execute(text(
            "UPDATE schedule_sheet SET ss_section_code='01' "
            "WHERE ss_section_code IS NULL OR TRIM(ss_section_code)=''"
        ))
        connection.execute(text(
            "UPDATE schedule_sheet SET ss_section_name=CONCAT('教学班', ss_section_code) "
            "WHERE ss_section_name IS NULL OR TRIM(ss_section_name)=''"
        ))

        inspector = inspect(connection)
        indexes = {index["name"] for index in inspector.get_indexes("schedule_sheet")}
        if "uq_schedule_course_term_section" not in indexes:
            connection.execute(text(
                "CREATE UNIQUE INDEX uq_schedule_course_term_section "
                "ON schedule_sheet (c_no, ss_year, ss_term, ss_section_code)"
            ))
        if "ss_fk_tcss_no" in indexes:
            connection.execute(text("DROP INDEX ss_fk_tcss_no ON schedule_sheet"))


if __name__ == "__main__":
    migrate()
    print("legacy teaching-section migration completed")
