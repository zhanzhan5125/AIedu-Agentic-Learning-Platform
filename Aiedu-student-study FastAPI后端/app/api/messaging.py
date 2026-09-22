from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, NotFound
from app.core.responses import ok
from app.db import get_db
from app.dependencies import current_user, require_roles
from app.models import (
    CommunicationKind,
    CommunicationMember,
    CommunicationMessage,
    CommunicationThread,
    CourseOffering,
    Enrollment,
    Notification,
    Role,
    User,
)
from app.schemas import AnnouncementCreate, CommunicationMessageCreate, DirectThreadCreate
from app.services.access import offering_for_user, same_offering_member
from app.integrations.realtime import publish_message

router = APIRouter(prefix="/messages", tags=["课程消息"])


def member_thread(db: Session, thread_id: int, user_id: int) -> CommunicationThread:
    thread = db.scalar(select(CommunicationThread).join(CommunicationMember).where(
        CommunicationThread.id == thread_id, CommunicationMember.user_id == user_id
    ))
    if thread is None:
        raise NotFound("会话不存在")
    return thread


def append(db: Session, thread: CommunicationThread, sender_id: int | None, body: str,
           message_type: str = "text") -> CommunicationMessage:
    message = CommunicationMessage(thread_id=thread.id, sender_id=sender_id,
                                   body=body, message_type=message_type)
    thread.last_message_at = datetime.now()
    db.add(message)
    return message


@router.get("/unread-summary")
def unread_summary(request: Request, offering_id: int | None = None,
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    if offering_id is not None:
        offering_for_user(db, offering_id, user)
    message_filters = [
        CommunicationMember.user_id == user.id,
        CommunicationMessage.id > func.coalesce(CommunicationMember.last_read_message_id, 0),
        CommunicationMessage.sender_id != user.id,
    ]
    notification_filters = [Notification.user_id == user.id, Notification.is_read.is_(False)]
    if offering_id is not None:
        message_filters.append(CommunicationThread.offering_id == offering_id)
        notification_filters.append(Notification.offering_id == offering_id)
    message_unread = db.scalar(
        select(func.count(CommunicationMessage.id))
        .join(CommunicationThread, CommunicationThread.id == CommunicationMessage.thread_id)
        .join(CommunicationMember, CommunicationMember.thread_id == CommunicationThread.id)
        .where(*message_filters)
    ) or 0
    notification_unread = db.scalar(
        select(func.count(Notification.id)).where(*notification_filters)
    ) or 0
    return ok({"message_unread": message_unread,
               "notification_unread": notification_unread,
               "total": message_unread + notification_unread}, request.state.request_id)


@router.get("/offerings/{offering_id}/contacts")
def list_contacts(offering_id: int, request: Request, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    offering = offering_for_user(db, offering_id, user)
    student_ids = select(Enrollment.student_id).where(Enrollment.offering_id == offering_id)
    rows = db.scalars(select(User).where(
        User.id.in_(student_ids.union_all(select(User.id).where(User.id == offering.teacher_id))),
        User.id != user.id, User.is_active.is_(True),
    ).order_by(User.role, User.display_name)).all()
    return ok([{"id": row.id, "name": row.display_name, "account": row.account,
                "role": row.role.value} for row in rows], request.state.request_id)


@router.get("/threads")
def list_threads(request: Request, offering_id: int | None = None,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = (select(CommunicationThread)
             .join(CommunicationMember)
             .where(CommunicationMember.user_id == user.id))
    if offering_id:
        query = query.where(CommunicationThread.offering_id == offering_id)
    rows = db.scalars(query.order_by(CommunicationThread.last_message_at.desc(),
                                     CommunicationThread.id.desc())).all()
    records = []
    for row in rows:
        member = db.scalar(select(CommunicationMember).where(
            CommunicationMember.thread_id == row.id, CommunicationMember.user_id == user.id))
        unread = db.scalar(select(func.count(CommunicationMessage.id)).where(
            CommunicationMessage.thread_id == row.id,
            CommunicationMessage.id > (member.last_read_message_id or 0),
            CommunicationMessage.sender_id != user.id,
        )) or 0
        last = db.scalar(select(CommunicationMessage).where(
            CommunicationMessage.thread_id == row.id).order_by(CommunicationMessage.id.desc()).limit(1))
        title = row.title
        if row.kind == CommunicationKind.direct and not title:
            peer_names = db.scalars(
                select(User.display_name)
                .join(CommunicationMember, CommunicationMember.user_id == User.id)
                .where(CommunicationMember.thread_id == row.id, User.id != user.id)
                .order_by(User.display_name)
            ).all()
            title = "、".join(peer_names) or "私聊"
        records.append({"id": row.id, "offering_id": row.offering_id, "kind": row.kind.value,
                        "title": title, "last_message_at": row.last_message_at,
                        "last_message": last.body[:100] if last else None, "unread_count": unread})
    return ok({"records": records, "unread_count": sum(item["unread_count"] for item in records)},
              request.state.request_id)


@router.post("/direct-threads", status_code=status.HTTP_201_CREATED)
def create_direct_thread(payload: DirectThreadCreate, request: Request,
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    offering = offering_for_user(db, payload.offering_id, user)
    if payload.recipient_id == user.id or not same_offering_member(db, offering, payload.recipient_id):
        raise Forbidden("只能联系同一教学班的教师或学生")
    recipient = db.get(User, payload.recipient_id)
    if recipient is None or not recipient.is_active:
        raise NotFound("联系人不存在")
    # Students can only create one-to-one threads; this model always creates exactly two members.
    candidates = db.scalars(select(CommunicationThread).join(CommunicationMember).where(
        CommunicationThread.offering_id == payload.offering_id,
        CommunicationThread.kind == CommunicationKind.direct,
        CommunicationMember.user_id == user.id,
    )).all()
    for thread in candidates:
        members = set(db.scalars(select(CommunicationMember.user_id).where(
            CommunicationMember.thread_id == thread.id)).all())
        if members == {user.id, payload.recipient_id}:
            return ok({"id": thread.id}, request.state.request_id)
    thread = CommunicationThread(offering_id=payload.offering_id, kind=CommunicationKind.direct,
                                 title=None, created_by=user.id)
    db.add(thread)
    db.flush()
    db.add_all([CommunicationMember(thread_id=thread.id, user_id=user.id),
                CommunicationMember(thread_id=thread.id, user_id=payload.recipient_id)])
    db.commit()
    return ok({"id": thread.id}, request.state.request_id)


@router.post("/offerings/{offering_id}/announcements", status_code=status.HTTP_201_CREATED)
def create_announcement(offering_id: int, payload: AnnouncementCreate, request: Request,
                        user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    offering = offering_for_user(db, offering_id, user)
    thread = CommunicationThread(offering_id=offering_id, kind=CommunicationKind.announcement,
                                 title=payload.title, created_by=user.id)
    db.add(thread)
    db.flush()
    student_ids = db.scalars(select(Enrollment.student_id).where(Enrollment.offering_id == offering_id)).all()
    db.add_all([CommunicationMember(thread_id=thread.id, user_id=value)
                for value in {user.id, *student_ids}])
    message = append(db, thread, user.id, payload.body, "announcement")
    db.commit()
    publish_message(set(student_ids), {"id": message.id, "thread_id": thread.id,
                                      "sender_id": user.id, "body": message.body,
                                      "message_type": message.message_type,
                                      "created_at": message.created_at})
    return ok({"thread_id": thread.id, "message_id": message.id}, request.state.request_id)


@router.get("/threads/{thread_id}")
def list_thread_messages(thread_id: int, request: Request, user: User = Depends(current_user),
                         db: Session = Depends(get_db)):
    member_thread(db, thread_id, user.id)
    rows = db.execute(select(CommunicationMessage, User).outerjoin(
        User, User.id == CommunicationMessage.sender_id).where(
        CommunicationMessage.thread_id == thread_id).order_by(CommunicationMessage.id)).all()
    return ok({"records": [{"id": message.id, "sender_id": message.sender_id,
                            "sender_name": sender.display_name if sender else "系统",
                            "body": message.body, "message_type": message.message_type,
                            "created_at": message.created_at} for message, sender in rows]},
              request.state.request_id)


@router.post("/threads/{thread_id}", status_code=status.HTTP_201_CREATED)
def send_message(thread_id: int, payload: CommunicationMessageCreate, request: Request,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    thread = member_thread(db, thread_id, user.id)
    if thread.kind in (CommunicationKind.announcement, CommunicationKind.system) and user.role != Role.teacher:
        raise Forbidden("学生不能向全体发送消息")
    message = append(db, thread, user.id, payload.body)
    db.commit()
    db.refresh(message)
    recipients = set(db.scalars(select(CommunicationMember.user_id).where(
        CommunicationMember.thread_id == thread.id,
        CommunicationMember.user_id != user.id,
    )).all())
    publish_message(recipients, {"id": message.id, "thread_id": thread.id,
                                 "sender_id": user.id, "body": message.body,
                                 "message_type": message.message_type,
                                 "created_at": message.created_at})
    return ok({"id": message.id}, request.state.request_id)


@router.put("/threads/{thread_id}/read")
def mark_thread_read(thread_id: int, request: Request, user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    member_thread(db, thread_id, user.id)
    member = db.scalar(select(CommunicationMember).where(
        CommunicationMember.thread_id == thread_id, CommunicationMember.user_id == user.id))
    member.last_read_message_id = db.scalar(select(func.max(CommunicationMessage.id)).where(
        CommunicationMessage.thread_id == thread_id))
    db.commit()
    return ok(None, request.state.request_id)
