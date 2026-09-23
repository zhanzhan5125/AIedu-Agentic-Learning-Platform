from __future__ import annotations

from datetime import datetime, timedelta

import csv
import io

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound
from app.core.responses import ok
from app.db import get_db
from app.dependencies import require_roles
from app.models import (
    Answer,
    Assignment,
    AssignmentQuestion,
    AssignmentStatus,
    CourseOffering,
    Enrollment,
    Notification,
    OutboxEvent,
    KnowledgePoint,
    Question,
    QuestionKnowledgePoint,
    Role,
    Submission,
    SubmissionStatus,
    ScheduledNotification,
    User,
)
from app.schemas import (AssignmentCreate, AssignmentPublish, AssignmentReplace, GradeRequest,
                         QuestionCreate, SubmissionSave)
from app.core.config import get_settings
from app.services.learning import refresh_class_mastery, refresh_student_mastery, upsert_evidence
from app.integrations.realtime import publish_message

router = APIRouter(tags=["作业"])

SUBMITTED_STATUSES = (
    SubmissionStatus.submitted,
    SubmissionStatus.ai_grading,
    SubmissionStatus.needs_review,
    SubmissionStatus.graded,
    SubmissionStatus.returned,
)


def submission_counts(db: Session, assignment: Assignment) -> dict[str, int]:
    assigned = db.scalar(select(func.count(Enrollment.id)).where(
        Enrollment.offering_id == assignment.offering_id)) or 0
    grouped = dict(db.execute(
        select(Submission.status, func.count(Submission.id))
        .where(Submission.assignment_id == assignment.id)
        .group_by(Submission.status)
    ).all())
    submitted = sum(grouped.get(state, 0) for state in SUBMITTED_STATUSES)
    return {
        "assigned_count": assigned,
        "submitted_count": submitted,
        "not_submitted_count": max(assigned - submitted, 0),
        "pending_grading_count": grouped.get(SubmissionStatus.submitted, 0),
        "ai_processing_count": grouped.get(SubmissionStatus.ai_grading, 0),
        "pending_teacher_review_count": grouped.get(SubmissionStatus.needs_review, 0),
        "graded_count": grouped.get(SubmissionStatus.graded, 0) + grouped.get(SubmissionStatus.returned, 0),
    }


def teacher_assignment(db: Session, assignment_id: int, teacher_id: int) -> Assignment:
    assignment = db.scalar(
        select(Assignment)
        .join(CourseOffering, CourseOffering.id == Assignment.offering_id)
        .where(Assignment.id == assignment_id, CourseOffering.teacher_id == teacher_id)
    )
    if assignment is None:
        raise NotFound("作业不存在")
    return assignment


def validate_knowledge_points(
    db: Session, assignment: Assignment, knowledge_point_ids: list[int],
) -> set[int]:
    ids = set(knowledge_point_ids)
    if not ids:
        return ids
    course_id = db.scalar(select(CourseOffering.course_id).where(
        CourseOffering.id == assignment.offering_id
    ))
    valid = set(db.scalars(select(KnowledgePoint.id).where(
        KnowledgePoint.course_id == course_id,
        KnowledgePoint.id.in_(ids),
    )).all())
    if valid != ids:
        raise Conflict("包含不属于该课程的知识点")
    return ids


def bind_question_knowledge_points(
    db: Session, question_id: int, knowledge_point_ids: set[int],
) -> None:
    for knowledge_point_id in sorted(knowledge_point_ids):
        db.add(QuestionKnowledgePoint(
            question_id=question_id, knowledge_point_id=knowledge_point_id, weight=100,
        ))


@router.get("/teacher/assignments")
def list_teacher_assignments(
    offering_id: int,
    request: Request,
    assignment_status: AssignmentStatus | None = Query(default=None, alias="status"),
    origin: str | None = Query(default=None, max_length=32),
    include_drafts: bool = Query(default=True),
    user: User = Depends(require_roles(Role.teacher)),
    db: Session = Depends(get_db),
):
    owns = db.scalar(select(CourseOffering.id).where(CourseOffering.id == offering_id, CourseOffering.teacher_id == user.id))
    if not owns:
        raise Forbidden("无权访问该课程")
    query = select(Assignment).where(Assignment.offering_id == offering_id)
    if assignment_status is not None:
        query = query.where(Assignment.status == assignment_status)
    elif not include_drafts:
        query = query.where(Assignment.status != AssignmentStatus.draft)
    if origin:
        query = query.where(Assignment.origin == origin)
    rows = db.scalars(query.order_by(Assignment.updated_at.desc(), Assignment.id.desc())).all()
    records = []
    for row in rows:
        records.append({
            "id": row.id, "title": row.title, "version": row.version,
            "status": row.status.value, "start_at": row.start_at, "end_at": row.end_at,
            "total_score": row.total_score, "origin": row.origin,
            "agent_run_id": row.agent_run_id, "created_at": row.created_at,
            "updated_at": row.updated_at, **submission_counts(db, row),
        })
    return ok({"total": len(records), "page": 1, "page_size": len(records) or 1, "records": records}, request.state.request_id)


@router.get("/teacher/assignments/{assignment_id}")
def get_teacher_assignment(
    assignment_id: int,
    request: Request,
    user: User = Depends(require_roles(Role.teacher)),
    db: Session = Depends(get_db),
):
    assignment = teacher_assignment(db, assignment_id, user.id)
    rows = db.execute(
        select(AssignmentQuestion.position, Question)
        .join(Question, Question.id == AssignmentQuestion.question_id)
        .where(AssignmentQuestion.assignment_id == assignment_id)
        .order_by(AssignmentQuestion.position)
    ).all()
    question_ids = [question.id for _, question in rows]
    point_rows = db.execute(select(
        QuestionKnowledgePoint.question_id, QuestionKnowledgePoint.knowledge_point_id,
    ).where(QuestionKnowledgePoint.question_id.in_(question_ids))).all() if question_ids else []
    point_ids_by_question: dict[int, list[int]] = {}
    for question_id, knowledge_point_id in point_rows:
        point_ids_by_question.setdefault(question_id, []).append(knowledge_point_id)
    questions = [{
        "id": question.id,
        "position": position,
        "kind": question.kind,
        "prompt": question.prompt,
        "reference_answer": question.reference_answer,
        "score": question.score,
        "difficulty": question.difficulty,
        "knowledge_point_ids": sorted(point_ids_by_question.get(question.id, [])),
    } for position, question in rows]
    return ok({
        "id": assignment.id,
        "title": assignment.title,
        "version": assignment.version,
        "status": assignment.status.value,
        "start_at": assignment.start_at,
        "end_at": assignment.end_at,
        "total_score": assignment.total_score,
        "origin": assignment.origin,
        "agent_run_id": assignment.agent_run_id,
        "created_at": assignment.created_at,
        "updated_at": assignment.updated_at,
        "questions": questions,
        **submission_counts(db, assignment),
    }, request.state.request_id)


@router.post("/teacher/assignments", status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignmentCreate,
    request: Request,
    user: User = Depends(require_roles(Role.teacher)),
    db: Session = Depends(get_db),
):
    offering = db.scalar(select(CourseOffering).where(CourseOffering.id == payload.offering_id, CourseOffering.teacher_id == user.id))
    if offering is None:
        raise Forbidden("无权在该课程创建作业")
    assignment = Assignment(**payload.model_dump(), status=AssignmentStatus.draft)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return ok({"id": assignment.id}, request.state.request_id)


@router.post("/teacher/assignments/{assignment_id}/questions", status_code=status.HTTP_201_CREATED)
def add_question(assignment_id: int, payload: QuestionCreate, request: Request,
                 user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    assignment = teacher_assignment(db, assignment_id, user.id)
    if assignment.status != AssignmentStatus.draft:
        raise Conflict("已发布作业不能直接修改题目")
    max_position = db.scalar(select(func.max(AssignmentQuestion.position)).where(
        AssignmentQuestion.assignment_id == assignment_id)) or 0
    point_ids = validate_knowledge_points(db, assignment, payload.knowledge_point_ids)
    question = Question(**payload.model_dump(exclude={"knowledge_point_ids"}))
    db.add(question)
    db.flush()
    db.add(AssignmentQuestion(assignment_id=assignment_id, question_id=question.id,
                              position=max_position + 1))
    bind_question_knowledge_points(db, question.id, point_ids)
    assignment.total_score += question.score
    db.commit()
    return ok({"id": question.id, "position": max_position + 1}, request.state.request_id)


@router.delete("/teacher/assignments/{assignment_id}")
def delete_assignment(assignment_id: int, request: Request,
                      user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    assignment = teacher_assignment(db, assignment_id, user.id)
    if assignment.status != AssignmentStatus.draft:
        raise Conflict("只有草稿作业可以删除")
    old_question_ids = db.scalars(select(AssignmentQuestion.question_id).where(
        AssignmentQuestion.assignment_id == assignment_id
    )).all()
    db.query(AssignmentQuestion).filter(
        AssignmentQuestion.assignment_id == assignment_id
    ).delete(synchronize_session=False)
    if old_question_ids:
        db.query(QuestionKnowledgePoint).filter(
            QuestionKnowledgePoint.question_id.in_(old_question_ids)
        ).delete(synchronize_session=False)
        db.query(Question).filter(Question.id.in_(old_question_ids)).delete(
            synchronize_session=False
        )
    db.delete(assignment)
    db.commit()
    return ok(None, request.state.request_id)


@router.put("/teacher/assignments/{assignment_id}")
def replace_assignment(assignment_id: int, payload: AssignmentReplace, request: Request,
                       user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    assignment = teacher_assignment(db, assignment_id, user.id)
    if assignment.status != AssignmentStatus.draft:
        raise Conflict("已发布作业不能修改")
    old_question_ids = db.scalars(select(AssignmentQuestion.question_id).where(
        AssignmentQuestion.assignment_id == assignment_id)).all()
    db.query(AssignmentQuestion).filter(AssignmentQuestion.assignment_id == assignment_id).delete()
    if old_question_ids:
        db.query(QuestionKnowledgePoint).filter(
            QuestionKnowledgePoint.question_id.in_(old_question_ids)).delete(synchronize_session=False)
        db.query(Question).filter(Question.id.in_(old_question_ids)).delete(synchronize_session=False)
    assignment.title = payload.title.strip()
    assignment.total_score = 0
    for position, item in enumerate(payload.questions, 1):
        point_ids = validate_knowledge_points(db, assignment, item.knowledge_point_ids)
        question = Question(**item.model_dump(exclude={"knowledge_point_ids"}))
        db.add(question)
        db.flush()
        db.add(AssignmentQuestion(assignment_id=assignment.id, question_id=question.id,
                                  position=position))
        bind_question_knowledge_points(db, question.id, point_ids)
        assignment.total_score += question.score
    assignment.version += 1
    db.commit()
    return ok({"id": assignment.id, "version": assignment.version,
               "total_score": assignment.total_score}, request.state.request_id)


@router.post("/assignments/{assignment_id}/publish")
def publish_assignment(
    assignment_id: int,
    payload: AssignmentPublish,
    request: Request,
    user: User = Depends(require_roles(Role.teacher)),
    db: Session = Depends(get_db),
):
    assignment = teacher_assignment(db, assignment_id, user.id)
    if assignment.status != AssignmentStatus.draft:
        if assignment.start_at == payload.start_at and assignment.end_at == payload.end_at:
            return ok({"id": assignment.id, "status": assignment.status.value}, request.state.request_id)
        raise Conflict("作业已发布，不能覆盖发布内容")
    if payload.end_at <= payload.start_at:
        raise Conflict("截止时间必须晚于开始时间")
    question_stats = db.execute(
        select(func.count(AssignmentQuestion.id), func.coalesce(func.sum(Question.score), 0))
        .join(Question, Question.id == AssignmentQuestion.question_id)
        .where(AssignmentQuestion.assignment_id == assignment_id)
    ).one()
    if question_stats[0] == 0 or question_stats[1] <= 0:
        raise Conflict("作业必须至少包含一道有分值的题目")
    assignment.start_at = payload.start_at
    assignment.end_at = payload.end_at
    assignment.total_score = int(question_stats[1])
    assignment.status = AssignmentStatus.scheduled if payload.start_at > datetime.now() else AssignmentStatus.open
    student_ids = db.scalars(select(Enrollment.student_id).where(Enrollment.offering_id == assignment.offering_id)).all()
    existing_ids = set(db.scalars(select(Submission.student_id).where(Submission.assignment_id == assignment_id)).all())
    db.add_all([Submission(assignment_id=assignment_id, student_id=sid) for sid in student_ids if sid not in existing_ids])
    db.add_all([Notification(user_id=sid, offering_id=assignment.offering_id,
                             kind="assignment_published", title="新作业已发布",
                             body=f"{assignment.title} 已发布，请在截止时间前完成。") for sid in student_ids])
    db.add(OutboxEvent(topic=get_settings().rocketmq_topic, tag="assignment.published",
                       aggregate_id=str(assignment.id), payload={"event_type": "assignment.published",
                                                                    "assignment_id": assignment.id}))
    for hours in (24, 2):
        scheduled_at = assignment.end_at - timedelta(hours=hours)
        if scheduled_at > datetime.now():
            db.add(ScheduledNotification(
                offering_id=assignment.offering_id, assignment_id=assignment.id,
                kind="assignment_deadline", scheduled_at=scheduled_at,
                dedup_key=f"assignment:{assignment.id}:deadline:{hours}h",
                payload={"hours": hours, "title": assignment.title},
            ))
    db.commit()
    publish_message(set(student_ids), {
        "event_type": "notification", "offering_id": assignment.offering_id,
        "title": "新作业已发布", "body": f"{assignment.title} 已发布，请在截止时间前完成。",
    })
    return ok({"id": assignment.id, "status": assignment.status.value}, request.state.request_id)


@router.get("/student/assignments")
def list_student_assignments(
    offering_id: int,
    request: Request,
    user: User = Depends(require_roles(Role.student)),
    db: Session = Depends(get_db),
):
    enrolled = db.scalar(select(Enrollment.id).where(Enrollment.offering_id == offering_id, Enrollment.student_id == user.id))
    if not enrolled:
        raise Forbidden("未加入该课程")
    rows = db.execute(
        select(Assignment, Submission)
        .outerjoin(Submission, (Submission.assignment_id == Assignment.id) & (Submission.student_id == user.id))
        .where(Assignment.offering_id == offering_id, Assignment.status != AssignmentStatus.draft)
        .order_by(Assignment.start_at.desc())
    ).all()
    now = datetime.now()
    records = []
    for assignment, submission in rows:
        effective_status = submission.status.value if submission else SubmissionStatus.not_started.value
        records.append({"id": assignment.id, "title": assignment.title, "start_at": assignment.start_at,
                        "end_at": assignment.end_at, "status": effective_status,
                        "overdue": bool(assignment.end_at and assignment.end_at < now)})
    return ok({"total": len(records), "page": 1, "page_size": len(records) or 1, "records": records}, request.state.request_id)


def student_submission(db: Session, assignment_id: int, student_id: int) -> tuple[Assignment, Submission]:
    row = db.execute(
        select(Assignment, Submission)
        .join(Submission, Submission.assignment_id == Assignment.id)
        .where(Assignment.id == assignment_id, Submission.student_id == student_id)
    ).one_or_none()
    if row is None:
        raise NotFound("作业或提交记录不存在")
    return row[0], row[1]


def student_assignment_detail(db: Session, assignment: Assignment, submission: Submission) -> dict:
    """Build the single contract used by both the answering and result pages."""
    question_rows = db.execute(
        select(AssignmentQuestion.position, Question)
        .join(Question, Question.id == AssignmentQuestion.question_id)
        .where(AssignmentQuestion.assignment_id == assignment.id)
        .order_by(AssignmentQuestion.position)
    ).all()
    answers = {
        row.question_id: row
        for row in db.scalars(select(Answer).where(Answer.submission_id == submission.id)).all()
    }
    result_visible = submission.status in (SubmissionStatus.graded, SubmissionStatus.returned)
    questions = []
    for position, question in question_rows:
        answer = answers.get(question.id)
        questions.append({
            "id": question.id,
            "position": position,
            "kind": question.kind,
            "prompt": question.prompt,
            "score": question.score,
            "difficulty": question.difficulty,
            "answer_id": answer.id if answer else None,
            "answer": answer.content if answer else "",
            # 标准答案、得分与评语只在教师确认成绩后返回，防止开放作业泄题。
            "reference_answer": question.reference_answer if result_visible else None,
            "earned_score": answer.score if answer and result_visible else None,
            "ai_comment": answer.ai_comment if answer and result_visible else None,
            "teacher_comment": answer.teacher_comment if answer and result_visible else None,
        })
    return {
        "id": assignment.id,
        "title": assignment.title,
        "offering_id": assignment.offering_id,
        "start_at": assignment.start_at,
        "end_at": assignment.end_at,
        "total_score": assignment.total_score,
        "submission": {
            "id": submission.id,
            "status": submission.status.value,
            "submitted_at": submission.submitted_at,
            "graded_at": submission.graded_at,
            "total_score": submission.total_score if result_visible else None,
            "ai_comment": submission.ai_comment if result_visible else None,
            "teacher_comment": submission.teacher_comment if result_visible else None,
        },
        "result_visible": result_visible,
        "questions": questions,
    }


@router.get("/student/assignments/{assignment_id}")
def get_student_assignment(
    assignment_id: int,
    request: Request,
    user: User = Depends(require_roles(Role.student)),
    db: Session = Depends(get_db),
):
    assignment, submission = student_submission(db, assignment_id, user.id)
    return ok(student_assignment_detail(db, assignment, submission), request.state.request_id)


def apply_answers(db: Session, assignment_id: int, submission: Submission, payload: SubmissionSave) -> None:
    allowed = set(db.scalars(select(AssignmentQuestion.question_id).where(
        AssignmentQuestion.assignment_id == assignment_id)).all())
    if any(item.question_id not in allowed for item in payload.answers):
        raise Conflict("答案包含不属于该作业的题目")
    current = {row.question_id: row for row in db.scalars(
        select(Answer).where(Answer.submission_id == submission.id)).all()}
    for item in payload.answers:
        answer = current.get(item.question_id)
        if answer is None:
            db.add(Answer(submission_id=submission.id, question_id=item.question_id, content=item.content))
        else:
            answer.content = item.content


def reset_grading(db: Session, submission: Submission) -> None:
    """A pre-deadline edit invalidates any grading based on an older answer version."""
    answers = db.scalars(select(Answer).where(Answer.submission_id == submission.id)).all()
    for answer in answers:
        answer.score = 0
        answer.teacher_comment = None
        answer.ai_comment = None
        answer.ai_raw = None
    submission.total_score = 0
    submission.teacher_comment = None
    submission.ai_comment = None
    submission.ai_graded_at = None
    submission.graded_at = None
    submission.grading_source = None
    submission.review_reason = None
    submission.ai_confidence = None


@router.put("/student/assignments/{assignment_id}/submission")
def save_submission(
    assignment_id: int,
    payload: SubmissionSave,
    request: Request,
    user: User = Depends(require_roles(Role.student)),
    db: Session = Depends(get_db),
):
    assignment, submission = student_submission(db, assignment_id, user.id)
    now = datetime.now()
    if assignment.start_at and now < assignment.start_at:
        raise Conflict("作业尚未开始")
    if assignment.end_at and now >= assignment.end_at:
        raise Conflict("作业已截止")
    apply_answers(db, assignment_id, submission, payload)
    reset_grading(db, submission)
    # 保存新快照相当于继续编辑；若此后不再提交，Worker 会在截止时间自动提交该快照。
    submission.status = SubmissionStatus.draft
    db.commit()
    return ok({"submission_id": submission.id, "status": submission.status.value}, request.state.request_id)


@router.post("/student/assignments/{assignment_id}/submit")
def submit_assignment(
    assignment_id: int,
    request: Request,
    payload: SubmissionSave | None = None,
    user: User = Depends(require_roles(Role.student)),
    db: Session = Depends(get_db),
):
    assignment, submission = student_submission(db, assignment_id, user.id)
    now = datetime.now()
    if assignment.start_at and now < assignment.start_at:
        raise Conflict("作业尚未开始")
    if assignment.end_at and now >= assignment.end_at:
        raise Conflict("作业已截止")
    # 提交接口可携带当前页面答案，使“修改后未另点保存，直接提交”仍以当前内容为准。
    if payload is not None:
        apply_answers(db, assignment_id, submission, payload)
    reset_grading(db, submission)
    submission.status = SubmissionStatus.submitted
    submission.submitted_at = now
    db.commit()
    return ok({"submission_id": submission.id, "status": submission.status.value}, request.state.request_id)


@router.post("/teacher/submissions/{submission_id}/grade")
def grade_submission(
    submission_id: int,
    payload: GradeRequest,
    request: Request,
    user: User = Depends(require_roles(Role.teacher)),
    db: Session = Depends(get_db),
):
    submission = db.scalar(
        select(Submission).join(Assignment).join(CourseOffering).where(
            Submission.id == submission_id, CourseOffering.teacher_id == user.id
        )
    )
    if submission is None:
        raise NotFound("提交记录不存在")
    assignment = db.get(Assignment, submission.assignment_id)
    if submission.status in (SubmissionStatus.not_started, SubmissionStatus.draft):
        raise Conflict("学生尚未正式提交，不能批阅")
    answers = {row.id: row for row in db.scalars(select(Answer).where(Answer.submission_id == submission_id)).all()}
    question_scores = dict(db.execute(select(Question.id, Question.score)).all())
    total = 0
    for item in payload.items:
        answer = answers.get(item.answer_id)
        if answer is None:
            raise Conflict(f"答案 {item.answer_id} 不属于该提交")
        max_score = question_scores.get(answer.question_id, 0)
        if item.score > max_score:
            raise Conflict("题目得分不能超过题目分值")
        answer.score = item.score
        answer.teacher_comment = item.comment
        total += item.score
    submission.total_score = total
    submission.teacher_comment = payload.overall_comment
    submission.grading_source = (
        "ai_assisted" if submission.status == SubmissionStatus.needs_review or
        submission.ai_graded_at is not None else "manual"
    )
    submission.graded_at = datetime.now()
    submission.review_reason = None
    submission.status = SubmissionStatus.graded
    for answer in answers.values():
        max_score = question_scores.get(answer.question_id, 0)
        normalized = round(answer.score / max_score * 100) if max_score else 0
        for binding in db.scalars(select(QuestionKnowledgePoint).where(
            QuestionKnowledgePoint.question_id == answer.question_id
        )).all():
            upsert_evidence(
                db, student_id=submission.student_id, offering_id=assignment.offering_id,
                knowledge_point_id=binding.knowledge_point_id, source_type="assignment",
                source_id=answer.id, score=normalized, confidence=100,
            )
    refresh_student_mastery(db, submission.student_id, assignment.offering_id)
    refresh_class_mastery(db, assignment.offering_id)
    db.add(Notification(user_id=submission.student_id, offering_id=assignment.offering_id,
                        kind="grade_confirmed",
                        title="作业成绩已确认", body=f"{assignment.title} 已完成批阅。"))
    db.add(OutboxEvent(topic=get_settings().rocketmq_topic, tag="submission.graded",
                       aggregate_id=str(submission.id), payload={"event_type": "submission.graded",
                                                                    "submission_id": submission.id}))
    db.commit()
    publish_message([submission.student_id], {
        "event_type": "notification", "offering_id": assignment.offering_id,
        "title": "作业成绩已确认", "body": f"{assignment.title} 已完成批阅。",
    })
    return ok({"submission_id": submission.id, "total_score": total}, request.state.request_id)


@router.get("/teacher/submissions/{submission_id}")
def get_teacher_submission(
    submission_id: int,
    request: Request,
    user: User = Depends(require_roles(Role.teacher)),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(Submission, Assignment, User)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .join(CourseOffering, CourseOffering.id == Assignment.offering_id)
        .join(User, User.id == Submission.student_id)
        .where(Submission.id == submission_id, CourseOffering.teacher_id == user.id)
    ).one_or_none()
    if row is None:
        raise NotFound("提交记录不存在")
    submission, assignment, student = row
    answers = {answer.question_id: answer for answer in db.scalars(
        select(Answer).where(Answer.submission_id == submission_id)
    ).all()}
    question_rows = db.execute(
        select(AssignmentQuestion.position, Question)
        .join(Question, Question.id == AssignmentQuestion.question_id)
        .where(AssignmentQuestion.assignment_id == assignment.id)
        .order_by(AssignmentQuestion.position)
    ).all()
    questions = []
    for position, question in question_rows:
        answer = answers.get(question.id)
        questions.append({
            "id": question.id,
            "position": position,
            "kind": question.kind,
            "prompt": question.prompt,
            "reference_answer": question.reference_answer,
            "score": question.score,
            "answer_id": answer.id if answer else None,
            "answer": answer.content if answer else "",
            "earned_score": answer.score if answer else 0,
            "ai_comment": answer.ai_comment if answer else None,
            "teacher_comment": answer.teacher_comment if answer else None,
        })
    return ok({
        "id": submission.id,
        "status": submission.status.value,
        "assignment_id": assignment.id,
        "assignment_title": assignment.title,
        "student": {"id": student.id, "account": student.account,
                    "name": student.display_name},
        "total_score": submission.total_score,
        "overall_comment": submission.teacher_comment,
        "questions": questions,
    }, request.state.request_id)


@router.get("/teacher/assignments/{assignment_id}/submissions")
def list_assignment_submissions(
    assignment_id: int,
    request: Request,
    user: User = Depends(require_roles(Role.teacher)),
    db: Session = Depends(get_db),
):
    assignment = teacher_assignment(db, assignment_id, user.id)
    rows = db.execute(
        select(Submission, User)
        .join(User, User.id == Submission.student_id)
        .where(Submission.assignment_id == assignment_id,
               Submission.status.in_(SUBMITTED_STATUSES))
        .order_by(Submission.submitted_at.desc(), User.account)
    ).all()
    records = [{
        "id": submission.id,
        "student_id": student.id,
        "student_account": student.account,
        "student_name": student.display_name,
        "status": submission.status.value,
        "submitted_at": submission.submitted_at,
        "ai_graded_at": submission.ai_graded_at,
        "graded_at": submission.graded_at,
        "grading_source": submission.grading_source,
        "review_reason": submission.review_reason,
        "ai_confidence": submission.ai_confidence,
        "total_score": submission.total_score,
    } for submission, student in rows]
    return ok({
        **submission_counts(db, assignment),
        "total": len(records), "page": 1, "page_size": len(records) or 1,
        "records": records,
    }, request.state.request_id)


@router.get("/teacher/assignments/{assignment_id}/unsubmitted")
def unsubmitted_students(assignment_id: int, request: Request,
                         user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    assignment = teacher_assignment(db, assignment_id, user.id)
    rows = db.execute(
        select(User.id, User.account, User.display_name, Submission.status)
        .join(Enrollment, Enrollment.student_id == User.id)
        .outerjoin(Submission, (Submission.student_id == User.id) &
                   (Submission.assignment_id == assignment_id))
        .where(Enrollment.offering_id == assignment.offering_id,
               (Submission.id.is_(None)) | (Submission.status.in_([
                   SubmissionStatus.not_started, SubmissionStatus.draft
               ])))
        .order_by(User.account)
    ).all()
    records = [{"id": row.id, "account": row.account, "name": row.display_name,
                "status": row.status.value if row.status else SubmissionStatus.not_started.value} for row in rows]
    return ok({"total": len(records), "page": 1, "page_size": len(records) or 1,
               "records": records}, request.state.request_id)


@router.get("/teacher/assignments/{assignment_id}/grades.csv")
def export_grades(assignment_id: int, user: User = Depends(require_roles(Role.teacher)),
                  db: Session = Depends(get_db)):
    teacher_assignment(db, assignment_id, user.id)
    rows = db.execute(
        select(User.account, User.display_name, Submission.status, Submission.total_score,
               Submission.teacher_comment)
        .join(User, User.id == Submission.student_id)
        .where(Submission.assignment_id == assignment_id)
        .order_by(User.account)
    ).all()
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["学号", "姓名", "状态", "总分", "教师评语"])
    for row in rows:
        writer.writerow([row.account, row.display_name, row.status.value, row.total_score,
                         row.teacher_comment or ""])
    return Response(content=output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="assignment-{assignment_id}-grades.csv"'})
