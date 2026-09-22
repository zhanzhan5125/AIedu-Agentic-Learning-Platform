"""Replace placeholder teaching data with a consistent university demo dataset.

This intentionally preserves the legacy and v2 manager accounts. Run only after
creating a full database backup. The --apply flag prevents accidental execution.
"""
from __future__ import annotations

import argparse
import hashlib

from sqlalchemy import inspect, text

from app.core.config import get_settings
from app.db import engine
from scripts.migrate_legacy import migrate


TEACHERS = [
    ("T2026001", "张文博"),
    ("T2026002", "李若涵"),
    ("T2026003", "陈志远"),
    ("T2026004", "王思雨"),
    ("T2026005", "赵明哲"),
    ("T2026006", "刘欣怡"),
]

STUDENT_NAMES = [
    "周子涵", "林嘉怡", "陈浩宇", "沈欣妍", "吴宇轩", "郑思琪",
    "徐俊杰", "许雨桐", "孙睿哲", "胡雅雯", "朱晨曦", "高梓萱",
    "何嘉诚", "郭诗涵", "马致远", "罗欣悦", "梁博文", "宋雨欣",
    "谢承泽", "唐婉清", "韩子墨", "冯若彤", "曹景行", "邓语嫣",
]
STUDENTS = [(f"S2026{index:04d}", name) for index, name in enumerate(STUDENT_NAMES, 1)]

COURSES = [
    ("CS101", "程序设计基础", "T2026001"),
    ("CS201", "数据结构与算法", "T2026002"),
    ("CS301", "操作系统", "T2026003"),
    ("CS302", "数据库系统原理", "T2026004"),
    ("CS303", "计算机网络", "T2026005"),
    ("AI401", "人工智能导论", "T2026006"),
]


def enrollment_accounts(course_number: str) -> list[str]:
    accounts = [account for account, _ in STUDENTS]
    rules = {
        "CS101": accounts,
        "CS201": accounts[:18],
        "CS301": accounts[6:],
        "CS302": accounts[:12] + accounts[18:],
        "CS303": [account for index, account in enumerate(accounts, 1) if index % 3 != 0],
        "AI401": accounts[8:],
    }
    return rules[course_number]


def clear_and_seed_legacy() -> None:
    with engine.begin() as connection:
        current_database = connection.execute(text("SELECT DATABASE()")) .scalar_one()
        expected_database = get_settings().database_url.rsplit("/", 1)[-1].split("?", 1)[0]
        if current_database != expected_database:
            raise RuntimeError(f"拒绝执行：当前数据库 {current_database!r} 不是 {expected_database!r}")

        # Canonical v2 data referring to old teachers/students must be removed first.
        for table_name in (
            "chat_messages", "conversations", "answers", "submissions", "assignment_questions", "assignments", "questions",
            "enrollments", "course_offerings", "app_courses", "ai_jobs", "outbox_events",
            "prompt_versions", "prompt_templates", "notifications", "file_objects",
        ):
            connection.execute(text(f"DELETE FROM `{table_name}`"))
        connection.execute(text("DELETE FROM app_users WHERE role <> 'manager'"))

        # Remove the complete legacy teaching graph while preserving manager accounts.
        for table_name in (
            "total_sheet", "answer_sheet", "component_sheet", "homework_sheet", "problem",
            "performance_sheet", "schedule_sheet", "student", "teacher", "course",
        ):
            connection.execute(text(f"DELETE FROM `{table_name}`"))

        connection.execute(
            text("INSERT INTO teacher (t_account, t_name, t_pass, t_profile) "
                 "VALUES (:account, :name, :password, NULL)"),
            [{"account": account, "name": name,
              "password": hashlib.md5(account.encode()).hexdigest()}
             for account, name in TEACHERS],
        )
        connection.execute(
            text("INSERT INTO student (s_account, s_name, s_pass, s_profile) "
                 "VALUES (:account, :name, :password, NULL)"),
            [{"account": account, "name": name,
              "password": hashlib.md5(account.encode()).hexdigest()}
             for account, name in STUDENTS],
        )
        connection.execute(
            text("INSERT INTO course (c_number, c_name) VALUES (:number, :name)"),
            [{"number": number, "name": name} for number, name, _ in COURSES],
        )
        connection.execute(
            text("INSERT INTO schedule_sheet "
                 "(ss_year, ss_term, ss_status, ss_section_code, ss_section_name, t_no, c_no) "
                 "VALUES (2026, 1, '进行中', '01', '教学班01', :teacher, :course)"),
            [{"course": number, "teacher": teacher} for number, _, teacher in COURSES],
        )

        offering_ids = dict(connection.execute(text(
            "SELECT c_no, ss_id FROM schedule_sheet WHERE ss_year=2026 AND ss_term=1"
        )).all())
        enrollments = [
            {"offering_id": offering_ids[number], "student": account}
            for number, _, _ in COURSES
            for account in enrollment_accounts(number)
        ]
        connection.execute(
            text("INSERT INTO performance_sheet (ss_id, s_no, ps_comment) "
                 "VALUES (:offering_id, :student, NULL)"),
            enrollments,
        )


def ensure_legacy_uniqueness() -> None:
    desired = {
        "student": ("uq_student_account", "s_account"),
        "teacher": ("uq_teacher_account", "t_account"),
        "course": ("uq_course_number", "c_number"),
        "performance_sheet": ("uq_performance_offering_student", "ss_id, s_no"),
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table_name, (index_name, columns) in desired.items():
            existing = {index["name"] for index in inspector.get_indexes(table_name)}
            if index_name not in existing:
                connection.execute(text(
                    f"CREATE UNIQUE INDEX `{index_name}` ON `{table_name}` ({columns})"
                ))


def counts() -> dict[str, int]:
    tables = (
        "manager", "teacher", "student", "course", "schedule_sheet", "performance_sheet",
        "app_users", "app_courses", "course_offerings", "enrollments",
    )
    with engine.connect() as connection:
        return {name: connection.execute(text(f"SELECT COUNT(*) FROM `{name}`")).scalar_one()
                for name in tables}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="confirm destructive demo-data rebuild")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("未执行：必须显式传入 --apply")
    clear_and_seed_legacy()
    ensure_legacy_uniqueness()
    migrated = migrate()
    print({"legacy_to_v2": migrated, "counts": counts()})
