from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings
from app.core.errors import Unauthorized

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> tuple[bool, bool]:
    """Return (valid, should_upgrade). Legacy 32-char MD5 hashes upgrade on login."""
    if len(stored_hash) == 32 and all(ch in "0123456789abcdefABCDEF" for ch in stored_hash):
        value = hashlib.md5(password.encode("utf-8")).hexdigest()  # noqa: S324 - legacy migration only
        return secrets.compare_digest(value, stored_hash.lower()), True
    try:
        valid = password_hasher.verify(stored_hash, password)
        return valid, password_hasher.check_needs_rehash(stored_hash)
    except (VerifyMismatchError, InvalidHashError):
        return False, False


def create_token(user_id: int, role: str, token_type: str) -> tuple[str, str, datetime]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    delta = (
        timedelta(minutes=settings.access_token_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_days)
    )
    expires_at = now + delta
    jti = secrets.token_urlsafe(24)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": token_type,
        "jti": jti,
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256"), jti, expires_at


def decode_token(token: str, expected_type: str = "access") -> dict:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise Unauthorized() from exc
    if payload.get("type") != expected_type or not payload.get("sub") or not payload.get("jti"):
        raise Unauthorized()
    return payload

