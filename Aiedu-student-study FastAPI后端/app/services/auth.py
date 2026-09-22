from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Unauthorized
from app.core.security import create_token, hash_password, verify_password
from app.integrations.session_store import session_store
from app.models import User
from app.schemas import LoginRequest


def authenticate(db: Session, request: LoginRequest) -> tuple[User, str, str]:
    user = db.scalar(
        select(User).where(User.role == request.role, User.account == request.account)
    )
    if user is None or not user.is_active:
        raise Unauthorized("账号或密码错误")
    valid, should_upgrade = verify_password(request.password, user.password_hash)
    if not valid:
        raise Unauthorized("账号或密码错误")
    if should_upgrade:
        user.password_hash = hash_password(request.password)
        user.password_migrated = True
    access, _, _ = create_token(user.id, user.role.value, "access")
    refresh, refresh_jti, refresh_expiry = create_token(user.id, user.role.value, "refresh")
    session_store.allow_refresh(refresh_jti, refresh_expiry)
    db.commit()
    return user, access, refresh

