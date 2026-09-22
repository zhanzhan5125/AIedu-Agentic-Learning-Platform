from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.core.responses import ok
from app.db import get_db
from app.dependencies import require_roles
from app.models import PromptTemplate, PromptVersion, Role, User
from app.schemas import PromptCreate

router = APIRouter(prefix="/prompts", tags=["提示词"])


@router.get("")
def list_prompts(request: Request, _user: User = Depends(require_roles(Role.manager, Role.teacher)),
                 db: Session = Depends(get_db)):
    rows = db.scalars(select(PromptTemplate).order_by(PromptTemplate.purpose, PromptTemplate.name)).all()
    records = []
    for row in rows:
        latest = db.scalar(select(PromptVersion).where(PromptVersion.template_id == row.id)
                           .order_by(PromptVersion.version.desc()).limit(1))
        records.append({"id": row.id, "name": row.name, "purpose": row.purpose,
                        "active": row.is_active, "version": latest.version if latest else 0,
                        "content": (latest.content or {}).get("template", "") if latest else ""})
    return ok(records, request.state.request_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_prompt(payload: PromptCreate, request: Request,
                  user: User = Depends(require_roles(Role.manager, Role.teacher)), db: Session = Depends(get_db)):
    if db.scalar(select(PromptTemplate.id).where(PromptTemplate.name == payload.name)):
        raise Conflict("提示词名称已存在")
    template = PromptTemplate(name=payload.name, purpose=payload.purpose, is_active=payload.activate)
    db.add(template)
    db.flush()
    db.add(PromptVersion(template_id=template.id, version=1, content={"template": payload.content}, created_by=user.id))
    db.commit()
    return ok({"id": template.id, "version": 1}, request.state.request_id)


@router.post("/{template_id}/versions", status_code=status.HTTP_201_CREATED)
def add_version(template_id: int, payload: PromptCreate, request: Request,
                user: User = Depends(require_roles(Role.manager, Role.teacher)), db: Session = Depends(get_db)):
    template = db.get(PromptTemplate, template_id)
    if template is None:
        raise NotFound("提示词不存在")
    version = (db.scalar(select(func.max(PromptVersion.version)).where(PromptVersion.template_id == template_id)) or 0) + 1
    db.add(PromptVersion(template_id=template_id, version=version,
                         content={"template": payload.content}, created_by=user.id))
    if payload.activate:
        template.is_active = True
    db.commit()
    return ok({"id": template_id, "version": version}, request.state.request_id)


@router.put("/{template_id}/activate")
def activate_prompt(template_id: int, request: Request,
                    _user: User = Depends(require_roles(Role.manager)), db: Session = Depends(get_db)):
    template = db.get(PromptTemplate, template_id)
    if template is None:
        raise NotFound("提示词不存在")
    for item in db.scalars(select(PromptTemplate).where(
        PromptTemplate.purpose == template.purpose)).all():
        item.is_active = item.id == template_id
    db.commit()
    return ok({"id": template_id, "active": True}, request.state.request_id)
