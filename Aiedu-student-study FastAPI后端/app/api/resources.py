from __future__ import annotations

import hashlib
import io
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, Conflict, NotFound
from app.core.responses import ok
from app.db import get_db
from app.dependencies import current_user, require_roles
from app.integrations.object_storage import object_storage
from app.models import CourseResource, OutboxEvent, ProcessingStatus, Role, User
from app.services.access import offering_for_user

router = APIRouter(tags=["课程资料"])
ALLOWED = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
}


def content_disposition(disposition: str, filename: str) -> str:
    safe_ascii = "".join(char if char.isascii() and char not in '\"\\' else "_" for char in filename)
    return f'{disposition}; filename="{safe_ascii}"; filename*=UTF-8\'\'{quote(filename)}'


def validate_file_content(content: bytes, mime_type: str) -> None:
    if mime_type == "application/pdf":
        if not content.startswith(b"%PDF-"):
            raise AppError(400, "文件内容不是有效的 PDF")
        return
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
    except (zipfile.BadZipFile, OSError):
        raise AppError(400, "Office 文件内容无效")
    required = ("word/document.xml" if mime_type.endswith("wordprocessingml.document")
                else "ppt/presentation.xml")
    if required not in names:
        raise AppError(400, "文件内容与扩展名不匹配")


def resource_for_user(db: Session, resource_id: int, user: User) -> CourseResource:
    resource = db.get(CourseResource, resource_id)
    if resource is None or resource.deleted_at is not None:
        raise NotFound("课程资料不存在")
    offering_for_user(db, resource.offering_id, user)
    return resource


@router.post("/teacher/offerings/{offering_id}/resources", status_code=status.HTTP_201_CREATED)
async def upload_resource(offering_id: int, request: Request, file: UploadFile = File(...),
                          title: str | None = Form(default=None),
                          resource_type: str = Form(default="courseware"),
                          user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    offering_for_user(db, offering_id, user)
    if file.content_type not in ALLOWED:
        raise AppError(400, "仅支持 PDF、DOCX 和 PPTX 课程资料")
    if resource_type not in {"syllabus", "courseware", "textbook"}:
        raise AppError(400, "资料类型必须是教学大纲、课件或教材")
    settings = get_settings()
    content = await file.read(settings.max_upload_bytes + 1)
    if not content or len(content) > settings.max_upload_bytes:
        raise AppError(400, "文件为空或超过大小限制")
    validate_file_content(content, file.content_type)
    digest = hashlib.sha256(content).hexdigest()
    last_version = db.scalar(select(func.max(CourseResource.version)).where(
        CourseResource.offering_id == offering_id, CourseResource.sha256 == digest
    )) or 0
    version = last_version + 1
    suffix = ALLOWED[file.content_type]
    key = f"offerings/{offering_id}/{uuid.uuid4().hex}{suffix}"
    object_storage.put(key, content, file.content_type)
    resource = CourseResource(
        offering_id=offering_id, uploader_id=user.id,
        title=(title or Path(file.filename or "课程资料").stem)[:255],
        original_name=Path(file.filename or f"resource{suffix}").name,
        resource_type=resource_type,
        object_key=key, mime_type=file.content_type, size=len(content), sha256=digest,
        version=version, processing_status=ProcessingStatus.uploaded,
    )
    db.add(resource)
    db.flush()
    db.add(OutboxEvent(topic=settings.rocketmq_topic, tag="resource.ingest",
                       aggregate_id=str(resource.id), payload={"event_type": "resource.ingest", "resource_id": resource.id}))
    db.commit()
    db.refresh(resource)
    return ok({"id": resource.id, "status": resource.processing_status.value,
               "resource_type": resource.resource_type,
               "version": resource.version}, request.state.request_id)


@router.get("/offerings/{offering_id}/resources")
def list_resources(offering_id: int, request: Request, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    offering_for_user(db, offering_id, user)
    query = select(CourseResource).where(
        CourseResource.offering_id == offering_id, CourseResource.deleted_at.is_(None)
    )
    if user.role == Role.student:
        query = query.where(CourseResource.processing_status == ProcessingStatus.ready)
    rows = db.scalars(query.order_by(CourseResource.id.desc())).all()
    return ok([{"id": row.id, "title": row.title, "name": row.original_name,
                "resource_type": row.resource_type,
                "mime_type": row.mime_type, "size": row.size, "version": row.version,
                "status": row.processing_status.value, "page_count": row.page_count,
                "chunk_count": row.chunk_count, "embedding_model": row.embedding_model,
                "error_message": row.error_message if user.role == Role.teacher else None,
                "indexed_at": row.indexed_at, "created_at": row.created_at} for row in rows],
              request.state.request_id)


@router.get("/resources/{resource_id}/preview")
def preview_resource(resource_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    resource = resource_for_user(db, resource_id, user)
    if user.role == Role.student and resource.processing_status != ProcessingStatus.ready:
        raise Conflict("资料尚未处理完成")
    try:
        content = object_storage.get(resource.object_key)
    except FileNotFoundError:
        raise NotFound("资料文件不存在")
    return Response(content=content, media_type=resource.mime_type,
                    headers={"Content-Disposition": content_disposition("inline", resource.original_name)})


@router.get("/resources/{resource_id}/download")
def download_resource(resource_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    resource = resource_for_user(db, resource_id, user)
    try:
        content = object_storage.get(resource.object_key)
    except FileNotFoundError:
        raise NotFound("资料文件不存在")
    return Response(content=content, media_type=resource.mime_type,
                    headers={"Content-Disposition": content_disposition("attachment", resource.original_name)})


@router.post("/resources/{resource_id}/reindex", status_code=status.HTTP_202_ACCEPTED)
def reindex_resource(resource_id: int, request: Request,
                     user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    resource = resource_for_user(db, resource_id, user)
    resource.processing_status = ProcessingStatus.uploaded
    resource.error_message = None
    resource.chunk_count = None
    resource.embedding_model = None
    db.add(OutboxEvent(topic=get_settings().rocketmq_topic, tag="resource.reindex",
                       aggregate_id=str(resource.id), payload={"event_type": "resource.ingest", "resource_id": resource.id}))
    db.commit()
    return ok({"id": resource.id, "status": resource.processing_status.value}, request.state.request_id)


@router.delete("/resources/{resource_id}")
def delete_resource(resource_id: int, request: Request,
                    user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    resource = resource_for_user(db, resource_id, user)
    resource.deleted_at = datetime.now()
    resource.processing_status = ProcessingStatus.deleted
    db.add(OutboxEvent(topic=get_settings().rocketmq_topic, tag="resource.delete",
                       aggregate_id=str(resource.id), payload={"event_type": "resource.delete", "resource_id": resource.id}))
    db.commit()
    return ok(None, request.state.request_id)
