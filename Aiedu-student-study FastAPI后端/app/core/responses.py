from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    code: int = 1
    msg: str = "ok"
    data: T | None = None
    request_id: str | None = None


class Page(BaseModel, Generic[T]):
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    records: list[T]


def ok(data=None, request_id: str | None = None) -> dict:
    return {"code": 1, "msg": "ok", "data": data, "request_id": request_id}

