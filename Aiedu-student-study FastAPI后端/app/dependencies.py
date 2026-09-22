from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_token
from app.db import get_db
from app.integrations.session_store import session_store
from app.models import Role, User

bearer = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise Unauthorized()
    payload = decode_token(credentials.credentials)
    if session_store.is_revoked(payload["jti"]):
        raise Unauthorized()
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active or user.role.value != payload["role"]:
        raise Unauthorized()
    return user


def require_roles(*roles: Role) -> Callable:
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise Forbidden()
        return user

    return dependency

