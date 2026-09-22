from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, NotFound
from app.core.responses import ok
from app.db import get_db
from app.dependencies import current_user
from app.models import FileObject, User

router = APIRouter(prefix="/files", tags=["文件"])
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_file(request: Request, file: UploadFile = File(...),
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    settings = get_settings()
    if file.content_type not in ALLOWED_TYPES:
        raise AppError(400, "仅支持 JPG、PNG、WebP 或 PDF 文件")
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise AppError(400, "文件大小超过限制")
    suffix = Path(file.filename or "file").suffix.lower()[:10]
    storage_key = f"{user.id}/{uuid.uuid4().hex}{suffix}"
    root = Path(settings.upload_dir).resolve()
    target = (root / storage_key).resolve()
    if root not in target.parents:
        raise AppError(400, "无效文件名")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    record = FileObject(owner_id=user.id, storage_key=storage_key,
                        original_name=Path(file.filename or "file").name,
                        content_type=file.content_type or "application/octet-stream", size=len(content))
    db.add(record)
    db.commit()
    db.refresh(record)
    return ok({"id": record.id, "name": record.original_name, "size": record.size,
               "url": f"{settings.api_prefix}/files/{record.id}"}, request.state.request_id)


@router.get("")
def list_files(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(FileObject).where(FileObject.owner_id == user.id)
                      .order_by(FileObject.id.desc())).all()
    return ok([{"id": row.id, "name": row.original_name, "type": row.content_type,
                "size": row.size, "created_at": row.created_at} for row in rows], request.state.request_id)


@router.get("/{file_id}")
def download_file(file_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = db.scalar(select(FileObject).where(FileObject.id == file_id, FileObject.owner_id == user.id))
    if record is None:
        raise NotFound("文件不存在")
    target = (Path(get_settings().upload_dir).resolve() / record.storage_key).resolve()
    if not target.is_file():
        raise NotFound("文件内容不存在")
    return FileResponse(target, media_type=record.content_type, filename=record.original_name)
