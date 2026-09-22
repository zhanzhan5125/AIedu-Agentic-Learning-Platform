from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound
from app.core.responses import ok
from app.core.security import hash_password
from app.db import get_db
from app.dependencies import require_roles
from app.models import Role, User
from app.schemas import AdminUserCreate, PasswordReset

router = APIRouter(prefix="/admin", tags=["管理员"])


@router.get("/users")
def list_users(request: Request, role: Role | None = None, search: str = "", page: int = 1, page_size: int = 20,
               _admin: User = Depends(require_roles(Role.manager)), db: Session = Depends(get_db)):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    query = select(User)
    count_query = select(func.count(User.id))
    if role:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)
    if search:
        user_filter = User.account.contains(search) | User.display_name.contains(search)
        query = query.where(user_filter)
        count_query = count_query.where(user_filter)
    total = db.scalar(count_query) or 0
    rows = db.scalars(query.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    records = [{"id": row.id, "account": row.account, "name": row.display_name,
                "role": row.role.value, "active": row.is_active} for row in rows]
    return ok({"total": total, "page": page, "page_size": page_size, "records": records}, request.state.request_id)


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(payload: AdminUserCreate, request: Request,
                _admin: User = Depends(require_roles(Role.manager)), db: Session = Depends(get_db)):
    duplicate = db.scalar(select(User.id).where(User.role == payload.role, User.account == payload.account))
    if duplicate:
        raise Conflict("该角色账号已存在")
    user = User(role=payload.role, account=payload.account, display_name=payload.display_name,
                password_hash=hash_password(payload.password), password_migrated=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return ok({"id": user.id}, request.state.request_id)


@router.put("/users/{user_id}/password")
def reset_password(user_id: int, payload: PasswordReset, request: Request,
                   _admin: User = Depends(require_roles(Role.manager)), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("用户不存在")
    user.password_hash = hash_password(payload.password)
    user.password_migrated = True
    db.commit()
    return ok(None, request.state.request_id)


@router.delete("/users/{user_id}")
def deactivate_user(user_id: int, request: Request,
                    admin: User = Depends(require_roles(Role.manager)), db: Session = Depends(get_db)):
    if user_id == admin.id:
        raise Forbidden("不能停用当前管理员账号")
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("用户不存在")
    user.is_active = False
    db.commit()
    return ok(None, request.state.request_id)


@router.post("/users/batch-deactivate")
def batch_deactivate_users(user_ids: list[int], request: Request,
                           admin: User = Depends(require_roles(Role.manager)), db: Session = Depends(get_db)):
    ids = set(user_ids) - {admin.id}
    if ids:
        for user in db.scalars(select(User).where(User.id.in_(ids))).all():
            user.is_active = False
        db.commit()
    return ok({"count": len(ids)}, request.state.request_id)
