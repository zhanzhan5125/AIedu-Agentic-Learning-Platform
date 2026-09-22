"""Idempotently copy legacy accounts and course structure into the v2 schema.

Run only after ``alembic upgrade head`` and always against a database backup first.
The legacy and v2 tables may coexist in the same MySQL schema.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import MetaData, Table, inspect, select

from app.db import SessionLocal, engine
from app.core.security import hash_password
from app.models import (Answer, Assignment, AssignmentQuestion, AssignmentStatus, Course,
                        CourseOffering, Enrollment, OfferingStatus, Question, Role,
                        Submission, SubmissionStatus, User)


STATUS = {"进行中": OfferingStatus.active, "progress": OfferingStatus.active,
          "已结束": OfferingStatus.ended, "ended": OfferingStatus.ended}


def migrate() -> dict[str, int]:
    available = set(inspect(engine).get_table_names())
    required = {"manager", "teacher", "student", "course"}
    missing = required - available
    if missing:
        raise RuntimeError(f"缺少旧表：{', '.join(sorted(missing))}")
    metadata = MetaData()
    legacy = {name: Table(name, metadata, autoload_with=engine) for name in available
              if name in required | {"schedule_sheet", "performance_sheet"}}
    counts = {"users": 0, "courses": 0, "offerings": 0, "enrollments": 0,
              "assignments": 0, "questions": 0, "assignment_questions": 0,
              "submissions": 0, "answers": 0, "ambiguous_answers": 0,
              "orphan_records": 0}
    account_ids: dict[tuple[Role, str], int] = {}
    optional = {"schedule_sheet", "performance_sheet", "homework_sheet", "problem",
                "component_sheet", "total_sheet", "answer_sheet"}
    for name in optional & available:
        if name not in legacy:
            legacy[name] = Table(name, metadata, autoload_with=engine)
    with SessionLocal.begin() as db:
        for table_name, role, prefix in (("manager", Role.manager, "m"),
                                         ("teacher", Role.teacher, "t"),
                                         ("student", Role.student, "s")):
            for row in db.execute(select(legacy[table_name])).mappings():
                account = str(row[f"{prefix}_account"])
                user = db.scalar(select(User).where(User.role == role, User.account == account))
                if user is None:
                    password = str(row[f"{prefix}_pass"] or "")
                    migrated = not (len(password) == 32 and all(c in "0123456789abcdefABCDEF" for c in password))
                    user = User(role=role, account=account,
                                password_hash=hash_password(password) if migrated else password,
                                display_name=str(row[f"{prefix}_name"] or account),
                                avatar_url=row[f"{prefix}_profile"], password_migrated=migrated)
                    db.add(user)
                    db.flush()
                    counts["users"] += 1
                account_ids[(role, account)] = user.id
        course_ids: dict[str, int] = {}
        for row in db.execute(select(legacy["course"])).mappings():
            number = str(row["c_number"])
            course = db.scalar(select(Course).where(Course.number == number))
            if course is None:
                course = Course(number=number, name=str(row["c_name"] or number))
                db.add(course)
                db.flush()
                counts["courses"] += 1
            course_ids[number] = course.id
        if "schedule_sheet" in legacy:
            offering_ids: dict[int, int] = {}
            for row in db.execute(select(legacy["schedule_sheet"])).mappings():
                teacher_id = account_ids.get((Role.teacher, str(row["t_no"])))
                course_id = course_ids.get(str(row["c_no"]))
                if not teacher_id or not course_id:
                    continue
                section_code = str(row.get("ss_section_code") or "01")
                section_name = str(row.get("ss_section_name") or f"教学班{section_code}")
                offering = db.scalar(select(CourseOffering).where(
                    CourseOffering.course_id == course_id,
                    CourseOffering.year == row["ss_year"], CourseOffering.term == row["ss_term"],
                    CourseOffering.section_code == section_code))
                if offering is None:
                    offering = CourseOffering(course_id=course_id, teacher_id=teacher_id,
                                              year=row["ss_year"], term=row["ss_term"],
                                              section_code=section_code, section_name=section_name,
                                              status=STATUS.get(row["ss_status"], OfferingStatus.planned))
                    db.add(offering)
                    db.flush()
                    counts["offerings"] += 1
                else:
                    offering.teacher_id = teacher_id
                    offering.section_name = section_name
                offering_ids[row["ss_id"]] = offering.id
            if "performance_sheet" in legacy:
                for row in db.execute(select(legacy["performance_sheet"])).mappings():
                    offering_id = offering_ids.get(row["ss_id"])
                    student_id = account_ids.get((Role.student, str(row["s_no"])))
                    if not offering_id or not student_id:
                        continue
                    exists = db.scalar(select(Enrollment.id).where(
                        Enrollment.offering_id == offering_id, Enrollment.student_id == student_id))
                    if not exists:
                        db.add(Enrollment(offering_id=offering_id, student_id=student_id))
                        counts["enrollments"] += 1
            assignment_ids: dict[int, int] = {}
            if "homework_sheet" in legacy:
                now = datetime.now()
                for row in db.execute(select(legacy["homework_sheet"])).mappings():
                    offering_id = offering_ids.get(row["ss_id"])
                    if not offering_id:
                        counts["orphan_records"] += 1
                        continue
                    start_at, end_at = row["hs_start_time"], row["hs_end_time"]
                    if start_at and start_at > now:
                        state = AssignmentStatus.scheduled
                    elif end_at and end_at < now:
                        state = AssignmentStatus.closed
                    else:
                        state = AssignmentStatus.open
                    assignment = db.scalar(select(Assignment).where(
                        Assignment.offering_id == offering_id,
                        Assignment.title == str(row["hs_name"] or f"旧作业-{row['hs_id']}"),
                        Assignment.start_at == start_at, Assignment.end_at == end_at))
                    if assignment is None:
                        assignment = Assignment(offering_id=offering_id,
                            title=str(row["hs_name"] or f"旧作业-{row['hs_id']}"),
                            start_at=start_at, end_at=end_at, status=state,
                            total_score=int(row["hs_score"] or 0))
                        db.add(assignment)
                        db.flush()
                        counts["assignments"] += 1
                    assignment_ids[row["hs_id"]] = assignment.id

            question_ids: dict[int, int] = {}
            if "problem" in legacy:
                for row in db.execute(select(legacy["problem"])).mappings():
                    prompt = str(row["p_question"] or "")
                    question = db.scalar(select(Question).where(
                        Question.prompt == prompt,
                        Question.reference_answer == row["p_reference"],
                        Question.score == int(row["p_score"] or 0)))
                    if question is None:
                        question = Question(kind=str(row["p_type"] or "short_answer"), prompt=prompt,
                            reference_answer=row["p_reference"], score=int(row["p_score"] or 0),
                            difficulty=int(row["p_level"] or 0))
                        db.add(question)
                        db.flush()
                        counts["questions"] += 1
                    question_ids[row["p_id"]] = question.id

            legacy_question_assignments: dict[int, list[int]] = {}
            if "component_sheet" in legacy:
                next_positions: dict[int, int] = {}
                components = db.execute(select(legacy["component_sheet"]).order_by(
                    legacy["component_sheet"].c.hs_id, legacy["component_sheet"].c.cs_order,
                    legacy["component_sheet"].c.cs_id)).mappings()
                for row in components:
                    assignment_id = assignment_ids.get(row["hs_id"])
                    question_id = question_ids.get(row["p_id"])
                    if not assignment_id or not question_id:
                        counts["orphan_records"] += 1
                        continue
                    legacy_question_assignments.setdefault(row["p_id"], []).append(assignment_id)
                    exists = db.scalar(select(AssignmentQuestion.id).where(
                        AssignmentQuestion.assignment_id == assignment_id,
                        AssignmentQuestion.question_id == question_id))
                    if not exists:
                        position = next_positions.get(assignment_id, 0) + 1
                        next_positions[assignment_id] = position
                        db.add(AssignmentQuestion(assignment_id=assignment_id,
                                                  question_id=question_id, position=position))
                        counts["assignment_questions"] += 1

            submission_ids: dict[tuple[int, str], int] = {}
            if "total_sheet" in legacy:
                for row in db.execute(select(legacy["total_sheet"])).mappings():
                    assignment_id = assignment_ids.get(row["hs_id"])
                    student_id = account_ids.get((Role.student, str(row["s_no"])))
                    if not assignment_id or not student_id:
                        counts["orphan_records"] += 1
                        continue
                    if row["ts_score"] is not None:
                        state = SubmissionStatus.graded
                    elif row["ts_hand"] is not None:
                        state = SubmissionStatus.submitted
                    else:
                        state = SubmissionStatus.draft
                    submission = db.scalar(select(Submission).where(
                        Submission.assignment_id == assignment_id,
                        Submission.student_id == student_id))
                    if submission is None:
                        submission = Submission(assignment_id=assignment_id, student_id=student_id)
                        db.add(submission)
                        db.flush()
                        counts["submissions"] += 1
                    submission.status = state
                    submission.submitted_at = row["ts_hand"]
                    submission.total_score = int(row["ts_score"] or 0)
                    submission.teacher_comment = row["ts_t_check"]
                    submission.ai_comment = row["ts_llm_check"]
                    submission_ids[(assignment_id, str(row["s_no"]))] = submission.id

            if "answer_sheet" in legacy:
                for row in db.execute(select(legacy["answer_sheet"])).mappings():
                    candidate_assignments = legacy_question_assignments.get(row["p_id"], [])
                    if len(candidate_assignments) > 1:
                        counts["ambiguous_answers"] += 1
                    for assignment_id in candidate_assignments:
                        submission_id = submission_ids.get((assignment_id, str(row["s_no"])))
                        question_id = question_ids.get(row["p_id"])
                        if not submission_id or not question_id:
                            counts["orphan_records"] += 1
                            continue
                        answer = db.scalar(select(Answer).where(Answer.submission_id == submission_id,
                                                                Answer.question_id == question_id))
                        if answer is None:
                            answer = Answer(submission_id=submission_id, question_id=question_id)
                            db.add(answer)
                            counts["answers"] += 1
                        answer.content = row["as_answer"]
                        answer.score = int(row["as_score"] or 0)
                        answer.teacher_comment = row["t_check"]
                        answer.ai_comment = row["llm_check"]
                        answer.ai_raw = {"legacy_raw": row["llm_raw"]} if row["llm_raw"] else None
    return counts


if __name__ == "__main__":
    print(migrate())
