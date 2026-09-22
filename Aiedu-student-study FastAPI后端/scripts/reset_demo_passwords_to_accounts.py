"""Reset only the generated demo teacher/student passwords to their account names."""
from __future__ import annotations

import argparse
import hashlib

from sqlalchemy import text

from app.db import engine


def md5(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("未执行：必须显式传入 --apply")

    with engine.begin() as connection:
        teachers = [row[0] for row in connection.execute(text(
            "SELECT t_account FROM teacher WHERE t_account LIKE 'T2026%'"
        ))]
        students = [row[0] for row in connection.execute(text(
            "SELECT s_account FROM student WHERE s_account LIKE 'S2026%'"
        ))]
        for account in teachers:
            digest = md5(account)
            connection.execute(text(
                "UPDATE teacher SET t_pass=:password WHERE t_account=:account"
            ), {"password": digest, "account": account})
            connection.execute(text(
                "UPDATE app_users SET password_hash=:password, password_migrated=0 "
                "WHERE role='teacher' AND account=:account"
            ), {"password": digest, "account": account})
        for account in students:
            digest = md5(account)
            connection.execute(text(
                "UPDATE student SET s_pass=:password WHERE s_account=:account"
            ), {"password": digest, "account": account})
            connection.execute(text(
                "UPDATE app_users SET password_hash=:password, password_migrated=0 "
                "WHERE role='student' AND account=:account"
            ), {"password": digest, "account": account})
    print({"teachers_reset": len(teachers), "students_reset": len(students)})
