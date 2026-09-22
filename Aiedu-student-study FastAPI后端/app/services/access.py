from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, NotFound
from app.models import CourseOffering, Enrollment, Role, User


def offering_for_user(db: Session, offering_id: int, user: User) -> CourseOffering:
    offering = db.get(CourseOffering, offering_id)
    if offering is None:
        raise NotFound("开课不存在")
    if user.role == Role.teacher and offering.teacher_id == user.id:
        return offering
    if user.role == Role.student and db.scalar(select(Enrollment.id).where(
        Enrollment.offering_id == offering_id, Enrollment.student_id == user.id
    )):
        return offering
    if user.role == Role.manager:
        return offering
    raise Forbidden("无权访问该课程")


def same_offering_member(db: Session, offering: CourseOffering, user_id: int) -> bool:
    if offering.teacher_id == user_id:
        return True
    return bool(db.scalar(select(Enrollment.id).where(
        Enrollment.offering_id == offering.id, Enrollment.student_id == user_id
    )))
