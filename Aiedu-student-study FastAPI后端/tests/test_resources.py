from __future__ import annotations

import io
import zipfile
from contextlib import contextmanager
from datetime import datetime

import pytest

from app.db import SessionLocal
from app.integrations.rag import chunks, embed_texts
from app.models import (Course, CourseOffering, CourseResource, Enrollment,
                        OfferingStatus, OutboxEvent, ProcessingStatus, Role, User)
from app.worker import _process_resource, process_resource


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client, role: str, account: str) -> str:
    response = client.post("/api/v1/auth/login", json={
        "role": role, "account": account, "password": "password123"
    })
    assert response.status_code == 200
    return response.json()["data"]["token"]


def test_course_resource_upload_listing_and_download_for_both_roles(client, monkeypatch):
    stored: dict[str, bytes] = {}
    monkeypatch.setattr("app.api.resources.object_storage.put", lambda key, content, _: stored.update({key: content}))
    monkeypatch.setattr("app.api.resources.object_storage.get", lambda key: stored[key])

    with SessionLocal.begin() as db:
        teacher = db.query(User).filter_by(role=Role.teacher).one()
        student = db.query(User).filter_by(role=Role.student).one()
        course = Course(number="CS-RAG", name="知识库测试")
        db.add(course)
        db.flush()
        offering = CourseOffering(course_id=course.id, teacher_id=teacher.id, year=2026,
                                  term=1, status=OfferingStatus.active)
        db.add(offering)
        db.flush()
        db.add(Enrollment(offering_id=offering.id, student_id=student.id))
        offering_id = offering.id

    teacher_token = _login(client, "teacher", "teacher")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<document />")
    document = buffer.getvalue()
    response = client.post(
        f"/api/v1/teacher/offerings/{offering_id}/resources",
        headers=_headers(teacher_token),
        files={"file": ("课程讲义.docx", document, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert response.status_code == 201
    resource_id = response.json()["data"]["id"]
    with SessionLocal.begin() as db:
        resource = db.get(CourseResource, resource_id)
        assert resource.processing_status == ProcessingStatus.uploaded
        assert db.query(OutboxEvent).filter_by(aggregate_id=str(resource_id), tag="resource.ingest").count() == 1
        resource.processing_status = ProcessingStatus.ready
        resource.chunk_count = 3
        resource.embedding_model = "text-embedding-3-large"

    student_token = _login(client, "student", "student")
    listing = client.get(
        f"/api/v1/offerings/{offering_id}/resources", headers=_headers(student_token)
    ).json()["data"]
    assert listing[0]["chunk_count"] == 3
    assert listing[0]["embedding_model"] == "text-embedding-3-large"
    for token in (teacher_token, student_token):
        downloaded = client.get(f"/api/v1/resources/{resource_id}/download", headers=_headers(token))
        assert downloaded.status_code == 200
        assert downloaded.content == document
        assert "filename*=UTF-8''" in downloaded.headers["content-disposition"]


def test_chunking_retains_overlap_and_missing_embedding_key_is_explicit():
    values = list(chunks("第一段内容。" * 80, size=120, overlap=20))
    assert len(values) > 1
    assert all(0 < len(value) <= 120 for value in values)
    with pytest.raises(RuntimeError, match="AIEDU_AI_API_KEY"):
        embed_texts(["课程资料"])


def test_deleted_resource_skips_stale_ingest(monkeypatch):
    with SessionLocal.begin() as db:
        teacher = db.query(User).filter_by(role=Role.teacher).one()
        course = Course(number="CS-DELETED-RAG", name="删除资料测试")
        db.add(course)
        db.flush()
        offering = CourseOffering(course_id=course.id, teacher_id=teacher.id, year=2026,
                                  term=1, status=OfferingStatus.active)
        db.add(offering)
        db.flush()
        resource = CourseResource(
            offering_id=offering.id, uploader_id=teacher.id, title="已删除教材",
            resource_type="textbook", original_name="deleted.pdf", object_key="deleted.pdf",
            mime_type="application/pdf", size=10, sha256="a" * 64, version=1,
            processing_status=ProcessingStatus.deleted, deleted_at=datetime.now(),
        )
        db.add(resource)
        db.flush()
        resource_id = resource.id

    monkeypatch.setattr("app.worker.object_storage.get",
                        lambda _: pytest.fail("不应读取已删除资料"))
    monkeypatch.setattr("app.worker.index_resource",
                        lambda *_, **__: pytest.fail("不应索引已删除资料"))

    _process_resource({"event_type": "resource.ingest", "resource_id": resource_id})


def test_resource_lock_contention_is_retried(monkeypatch):
    @contextmanager
    def unavailable_lock(*_, **__):
        yield False

    monkeypatch.setattr("app.worker.runtime_cache.lock", unavailable_lock)
    with pytest.raises(RuntimeError, match="其他 Worker"):
        process_resource({"event_type": "resource.delete", "resource_id": 99})
