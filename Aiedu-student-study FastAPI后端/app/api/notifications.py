from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.core.responses import ok
from app.db import get_db
from app.dependencies import current_user
from app.models import Notification, User
from app.services.access import offering_for_user

router = APIRouter(prefix="/notifications", tags=["消息中心"])


@router.get("")
def list_notifications(request: Request, page: int = 1, page_size: int = 20,
                       offering_id: int | None = None,
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    filters = [Notification.user_id == user.id]
    if offering_id is not None:
        offering_for_user(db, offering_id, user)
        filters.append(Notification.offering_id == offering_id)
    total = db.scalar(select(func.count(Notification.id)).where(*filters)) or 0
    rows = db.scalars(select(Notification).where(*filters)
                      .order_by(Notification.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    records = [{"id": row.id, "kind": row.kind, "title": row.title, "body": row.body,
                "offering_id": row.offering_id, "is_read": row.is_read,
                "created_at": row.created_at} for row in rows]
    return ok({"total": total, "page": page, "page_size": page_size, "records": records}, request.state.request_id)


@router.put("/{notification_id}/read")
def mark_read(notification_id: int, request: Request, user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    changed = db.execute(update(Notification).where(Notification.id == notification_id,
                                                    Notification.user_id == user.id).values(is_read=True))
    if changed.rowcount == 0:
        raise NotFound("消息不存在")
    db.commit()
    return ok(None, request.state.request_id)
