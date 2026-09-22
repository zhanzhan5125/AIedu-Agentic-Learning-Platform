from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Unauthorized
from app.core.responses import ok
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.db import get_db
from app.dependencies import bearer, current_user
from app.integrations.session_store import session_store
from app.models import User
from app.schemas import LoginRequest, PasswordChange
from app.services.auth import authenticate

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user, access, refresh = authenticate(db, payload)
    response.set_cookie(
        "aiedu_refresh",
        refresh,
        httponly=True,
        secure=get_settings().env == "production",
        samesite="lax",
        max_age=get_settings().refresh_token_days * 86400,
        path=f"{get_settings().api_prefix}/auth",
    )
    return ok(
        {
            "id": user.id,
            "account": user.account,
            "name": user.display_name,
            "role": user.role.value,
            "image": user.avatar_url,
            "token": access,
        },
        request.state.request_id,
    )


@router.post("/refresh")
def refresh(request: Request, aiedu_refresh: str | None = Cookie(default=None)):
    if not aiedu_refresh:
        raise Unauthorized()
    payload = decode_token(aiedu_refresh, "refresh")
    if not session_store.refresh_exists(payload["jti"]) or session_store.is_revoked(payload["jti"]):
        raise Unauthorized()
    access, _, _ = create_token(int(payload["sub"]), payload["role"], "access")
    return ok({"token": access}, request.state.request_id)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    aiedu_refresh: str | None = Cookie(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    if credentials:
        access_payload = decode_token(credentials.credentials)
        access_expires = datetime.fromtimestamp(access_payload["exp"], timezone.utc)
        session_store.revoke(access_payload["jti"], access_expires, "access")
    if aiedu_refresh:
        payload = decode_token(aiedu_refresh, "refresh")
        expires = datetime.fromtimestamp(payload["exp"], timezone.utc)
        session_store.revoke(payload["jti"], expires, "refresh")
    response.delete_cookie("aiedu_refresh", path=f"{get_settings().api_prefix}/auth")
    return ok(None, request.state.request_id)


@router.get("/me")
def me(request: Request, user: User = Depends(current_user)):
    return ok(
        {
            "id": user.id,
            "account": user.account,
            "name": user.display_name,
            "role": user.role.value,
            "image": user.avatar_url,
        },
        request.state.request_id,
    )


@router.put("/password")
def change_password(
    payload: PasswordChange,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    valid, _ = verify_password(payload.old_password, user.password_hash)
    if not valid:
        raise Unauthorized("原密码错误")
    user.password_hash = hash_password(payload.new_password)
    user.password_migrated = True
    db.commit()
    return ok(None, request.state.request_id)
