from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.core.responses import ok
from app.db import get_db
from app.dependencies import require_roles
from app.models import Assignment, Course, CourseOffering, Enrollment, OfferingStatus, Role, User
from app.schemas import CourseCreate, EnrollmentCreate, OfferingCreate

router = APIRouter(tags=["课程"])


def _page(page: int, page_size: int) -> tuple[int, int]:
    return max(1, page), min(100, max(1, page_size))


@router.get("/admin/courses")
def admin_courses(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = "",
    _: User = Depends(require_roles(Role.manager)),
    db: Session = Depends(get_db),
):
    page, page_size = _page(page, page_size)
    filters = []
    if search:
        filters.append((Course.name.contains(search)) | (Course.number.contains(search)))
    total = db.scalar(select(func.count(Course.id)).where(*filters)) or 0
    rows = db.scalars(
        select(Course).where(*filters).order_by(Course.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    records = [{"id": row.id, "number": row.number, "name": row.name, "description": row.description} for row in rows]
    return ok({"total": total, "page": page, "page_size": page_size, "records": records}, request.state.request_id)


@router.post("/admin/courses", status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseCreate,
    request: Request,
    _: User = Depends(require_roles(Role.manager)),
    db: Session = Depends(get_db),
):
    exists = db.scalar(select(Course.id).where((Course.number == payload.number) | (Course.name == payload.name)))
    if exists:
        raise Conflict("课程编号或课程名称已存在")
    course = Course(**payload.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return ok({"id": course.id}, request.state.request_id)


@router.delete("/admin/courses/{course_id}")
def delete_course(
    course_id: int,
    request: Request,
    _: User = Depends(require_roles(Role.manager)),
    db: Session = Depends(get_db),
):
    course = db.get(Course, course_id)
    if course is None:
        raise NotFound("课程不存在")
    active = db.scalar(
        select(func.count(CourseOffering.id)).where(
            CourseOffering.course_id == course_id,
            CourseOffering.status.in_([OfferingStatus.planned, OfferingStatus.active]),
        )
    )
    if active:
        raise Conflict("课程存在未结束的开课，不能删除")
    db.delete(course)
    db.commit()
    return ok(None, request.state.request_id)


@router.get("/teacher/offerings")
def teacher_offerings(
    request: Request,
    user: User = Depends(require_roles(Role.teacher)),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(CourseOffering, Course)
        .join(Course, Course.id == CourseOffering.course_id)
        .where(CourseOffering.teacher_id == user.id)
        .order_by(CourseOffering.year.desc(), CourseOffering.term.desc())
    ).all()
    records = [
        {"id": offering.id, "course_id": course.id, "number": course.number, "title": course.name,
         "year": offering.year, "term": offering.term, "section_code": offering.section_code,
         "section_name": offering.section_name, "status": offering.status.value}
        for offering, course in rows
    ]
    return ok({"total": len(records), "page": 1, "page_size": len(records) or 1, "records": records}, request.state.request_id)


@router.get("/teacher/course-catalog")
def teacher_course_catalog(
    request: Request,
    search: str = "",
    _: User = Depends(require_roles(Role.teacher)),
    db: Session = Depends(get_db),
):
    filters = []
    if search:
        filters.append((Course.name.contains(search)) | (Course.number.contains(search)))
    rows = db.scalars(select(Course).where(*filters).order_by(Course.number)).all()
    records = [
        {"id": row.id, "number": row.number, "name": row.name, "description": row.description}
        for row in rows
    ]
    return ok({"total": len(records), "page": 1, "page_size": len(records) or 1,
               "records": records}, request.state.request_id)


@router.post("/teacher/offerings", status_code=status.HTTP_201_CREATED)
def create_offering(
    payload: OfferingCreate,
    request: Request,
    user: User = Depends(require_roles(Role.teacher)),
    db: Session = Depends(get_db),
):
    if db.get(Course, payload.course_id) is None:
        raise NotFound("课程不存在")
    exists = db.scalar(select(CourseOffering.id).where(
        CourseOffering.course_id == payload.course_id,
        CourseOffering.year == payload.year,
        CourseOffering.term == payload.term,
        CourseOffering.section_code == payload.section_code,
    ))
    if exists:
        raise Conflict("相同课程、学年、学期和教学班编号的开课已存在")
    values = payload.model_dump()
    values["section_code"] = values["section_code"].strip()
    values["section_name"] = (values["section_name"] or f"教学班{values['section_code']}").strip()
    offering = CourseOffering(**values, teacher_id=user.id, status=OfferingStatus.active)
    db.add(offering)
    db.commit()
    db.refresh(offering)
    return ok({"id": offering.id}, request.state.request_id)


@router.get("/student/courses")
def student_courses(
    request: Request,
    user: User = Depends(require_roles(Role.student)),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(CourseOffering, Course, User)
        .join(Enrollment, Enrollment.offering_id == CourseOffering.id)
        .join(Course, Course.id == CourseOffering.course_id)
        .join(User, User.id == CourseOffering.teacher_id)
        .where(Enrollment.student_id == user.id)
    ).all()
    records = [
        {"id": offering.id, "number": course.number, "title": course.name, "teacher": teacher.display_name,
         "year": offering.year, "term": offering.term, "section_code": offering.section_code,
         "section_name": offering.section_name, "status": offering.status.value}
        for offering, course, teacher in rows
    ]
    return ok({"total": len(records), "page": 1, "page_size": len(records) or 1, "records": records}, request.state.request_id)


@router.get("/teacher/offerings/{offering_id}/enrollments")
def list_enrollments(offering_id: int, request: Request,
                     user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    owned = db.scalar(select(CourseOffering.id).where(CourseOffering.id == offering_id,
                                                      CourseOffering.teacher_id == user.id))
    if not owned:
        raise NotFound("开课不存在")
    rows = db.execute(select(User.id, User.account, User.display_name)
                      .join(Enrollment, Enrollment.student_id == User.id)
                      .where(Enrollment.offering_id == offering_id).order_by(User.account)).all()
    records = [{"id": row.id, "account": row.account, "name": row.display_name} for row in rows]
    return ok({"total": len(records), "page": 1, "page_size": len(records) or 1,
               "records": records}, request.state.request_id)


@router.post("/teacher/offerings/{offering_id}/enrollments", status_code=status.HTTP_201_CREATED)
def add_enrollment(offering_id: int, payload: EnrollmentCreate, request: Request,
                   user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    owned = db.scalar(select(CourseOffering.id).where(CourseOffering.id == offering_id,
                                                      CourseOffering.teacher_id == user.id))
    if not owned:
        raise NotFound("开课不存在")
    student = db.scalar(select(User).where(User.role == Role.student,
                                           User.account == payload.student_account,
                                           User.is_active.is_(True)))
    if student is None:
        raise NotFound("学生不存在")
    existing = db.scalar(select(Enrollment).where(Enrollment.offering_id == offering_id,
                                                   Enrollment.student_id == student.id))
    if existing:
        return ok({"id": existing.id}, request.state.request_id)
    enrollment = Enrollment(offering_id=offering_id, student_id=student.id)
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return ok({"id": enrollment.id}, request.state.request_id)


@router.delete("/teacher/offerings/{offering_id}/enrollments/{student_id}")
def remove_enrollment(offering_id: int, student_id: int, request: Request,
                      user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    owned = db.scalar(select(CourseOffering.id).where(
        CourseOffering.id == offering_id, CourseOffering.teacher_id == user.id))
    if not owned:
        raise NotFound("开课不存在")
    enrollment = db.scalar(select(Enrollment).where(
        Enrollment.offering_id == offering_id, Enrollment.student_id == student_id))
    if enrollment is None:
        raise NotFound("学生不在该教学班")
    db.delete(enrollment)
    db.commit()
    return ok(None, request.state.request_id)


@router.post("/teacher/offerings/{offering_id}/enrollments/batch-remove")
def batch_remove_enrollments(offering_id: int, student_ids: list[int], request: Request,
                             user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    owned = db.scalar(select(CourseOffering.id).where(
        CourseOffering.id == offering_id, CourseOffering.teacher_id == user.id))
    if not owned:
        raise NotFound("开课不存在")
    count = db.query(Enrollment).filter(
        Enrollment.offering_id == offering_id,
        Enrollment.student_id.in_(set(student_ids)),
    ).delete(synchronize_session=False)
    db.commit()
    return ok({"count": count}, request.state.request_id)


@router.get("/admin/offerings")
def admin_offerings(request: Request, course_id: int | None = None, search: str = "",
                    page: int = 1, page_size: int = 20,
                    _: User = Depends(require_roles(Role.manager)), db: Session = Depends(get_db)):
    page, page_size = _page(page, page_size)
    filters = []
    if course_id:
        filters.append(CourseOffering.course_id == course_id)
    if search:
        filters.append(User.display_name.contains(search) | User.account.contains(search))
    base = select(CourseOffering, Course, User).join(Course).join(User, User.id == CourseOffering.teacher_id).where(*filters)
    rows = db.execute(base.order_by(CourseOffering.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    total = db.scalar(select(func.count(CourseOffering.id)).join(Course).join(
        User, User.id == CourseOffering.teacher_id).where(*filters)) or 0
    records = [{"id": offering.id, "course_id": course.id, "course_number": course.number,
                "course_name": course.name, "teacher_id": teacher.id,
                "teacher_account": teacher.account, "teacher_name": teacher.display_name,
                "year": offering.year, "term": offering.term,
                "section_code": offering.section_code, "section_name": offering.section_name,
                "status": offering.status.value} for offering, course, teacher in rows]
    return ok({"total": total, "page": page, "page_size": page_size, "records": records}, request.state.request_id)


@router.delete("/admin/offerings/{offering_id}")
def delete_offering(offering_id: int, request: Request,
                    _: User = Depends(require_roles(Role.manager)), db: Session = Depends(get_db)):
    offering = db.get(CourseOffering, offering_id)
    if offering is None:
        raise NotFound("开课不存在")
    if db.scalar(select(func.count(Assignment.id)).where(Assignment.offering_id == offering_id)):
        raise Conflict("教学班已有作业，不能直接删除")
    db.delete(offering)
    db.commit()
    return ok(None, request.state.request_id)
