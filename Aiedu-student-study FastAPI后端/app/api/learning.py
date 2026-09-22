from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound
from app.core.responses import ok
from app.db import get_db
from app.dependencies import current_user, require_roles
from app.models import (
    Assignment,
    AssignmentInsightSnapshot,
    AssignmentQuestion,
    CourseOffering,
    Enrollment,
    KnowledgePoint,
    Question,
    QuestionKnowledgePoint,
    Role,
    User,
)
from app.schemas import KnowledgePointCreate, QuestionKnowledgeBinding
from app.services.access import offering_for_user
from app.services.insights import assignment_insights, class_insights
from app.services.learning import profile_view

router = APIRouter(tags=["学情与知识点"])


@router.get("/courses/{course_id}/knowledge-points")
def list_knowledge_points(course_id: int, request: Request, user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    allowed = db.scalar(select(CourseOffering.id).where(
        CourseOffering.course_id == course_id,
        ((CourseOffering.teacher_id == user.id) if user.role == Role.teacher else CourseOffering.id.in_(
            select(Enrollment.offering_id).where(Enrollment.student_id == user.id)
        )),
    )) if user.role != Role.manager else True
    if not allowed:
        raise Forbidden("无权访问该课程知识点")
    rows = db.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id)
                      .order_by(KnowledgePoint.code)).all()
    return ok([{"id": row.id, "code": row.code, "name": row.name,
                "parent_id": row.parent_id, "description": row.description} for row in rows],
              request.state.request_id)


@router.post("/teacher/courses/{course_id}/knowledge-points", status_code=status.HTTP_201_CREATED)
def create_knowledge_point(course_id: int, payload: KnowledgePointCreate, request: Request,
                           user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    if not db.scalar(select(CourseOffering.id).where(
        CourseOffering.course_id == course_id, CourseOffering.teacher_id == user.id
    )):
        raise Forbidden("无权维护该课程知识点")
    if payload.parent_id and not db.scalar(select(KnowledgePoint.id).where(
        KnowledgePoint.id == payload.parent_id, KnowledgePoint.course_id == course_id
    )):
        raise Conflict("父知识点不属于该课程")
    if db.scalar(select(KnowledgePoint.id).where(
        KnowledgePoint.course_id == course_id, KnowledgePoint.code == payload.code
    )):
        raise Conflict("知识点编号已存在")
    point = KnowledgePoint(course_id=course_id, **payload.model_dump())
    db.add(point)
    db.commit()
    db.refresh(point)
    return ok({"id": point.id}, request.state.request_id)


@router.put("/teacher/questions/{question_id}/knowledge-points")
def bind_question_knowledge(question_id: int, payload: list[QuestionKnowledgeBinding], request: Request,
                            user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    question = db.scalar(select(Question).join(QuestionKnowledgePoint, isouter=True).where(Question.id == question_id))
    owns = db.scalar(select(Assignment.id).join(CourseOffering).where(
        Assignment.id.in_(select(AssignmentQuestion.assignment_id)
                          .where(AssignmentQuestion.question_id == question_id)),
        CourseOffering.teacher_id == user.id,
    ))
    if question is None or not owns:
        raise NotFound("题目不存在")
    ids = [item.knowledge_point_id for item in payload]
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.id.in_(ids))).all() if ids else []
    if len(points) != len(set(ids)):
        raise Conflict("包含不存在的知识点")
    db.query(QuestionKnowledgePoint).filter(QuestionKnowledgePoint.question_id == question_id).delete()
    db.add_all([QuestionKnowledgePoint(question_id=question_id, **item.model_dump()) for item in payload])
    db.commit()
    return ok({"question_id": question_id, "knowledge_point_count": len(payload)}, request.state.request_id)


@router.get("/teacher/offerings/{offering_id}/insights")
def offering_insights(offering_id: int, request: Request,
                      user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    offering = offering_for_user(db, offering_id, user)
    return ok(class_insights(db, offering.id), request.state.request_id)


@router.get("/teacher/offerings/{offering_id}/students/{student_id}/profile")
def teacher_student_profile(offering_id: int, student_id: int, request: Request,
                            user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    offering_for_user(db, offering_id, user)
    if not db.scalar(select(Enrollment.id).where(
        Enrollment.offering_id == offering_id, Enrollment.student_id == student_id
    )):
        raise NotFound("学生不在该教学班")
    return ok(profile_view(db, student_id, offering_id), request.state.request_id)


@router.get("/student/offerings/{offering_id}/learning-profile")
def student_profile(offering_id: int, request: Request,
                    user: User = Depends(require_roles(Role.student)), db: Session = Depends(get_db)):
    offering_for_user(db, offering_id, user)
    return ok(profile_view(db, user.id, offering_id), request.state.request_id)


@router.get("/teacher/assignments/{assignment_id}/insights")
def assignment_insight_view(assignment_id: int, request: Request,
                            user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    assignment = db.scalar(select(Assignment).join(CourseOffering).where(
        Assignment.id == assignment_id, CourseOffering.teacher_id == user.id
    ))
    if assignment is None:
        raise NotFound("作业不存在")
    data = assignment_insights(db, assignment)
    latest = db.scalar(select(AssignmentInsightSnapshot).where(
        AssignmentInsightSnapshot.assignment_id == assignment_id
    ).order_by(AssignmentInsightSnapshot.version.desc()).limit(1))
    data["snapshot_version"] = latest.version if latest else 0
    data["snapshot_at"] = latest.snapshot_at if latest else None
    return ok(data, request.state.request_id)
