from __future__ import annotations

import json

from app.ai import workflows
from app.ai.contracts import ChapterKnowledgeBatch, CourseChapterPlan
from app.db import SessionLocal
from app.models import (
    Course, CourseOffering, CourseResource, OfferingStatus, ProcessingStatus,
    ResourceChunk, Role, User,
)


def test_staged_course_map_uses_outline_then_chapter_specific_support(monkeypatch):
    with SessionLocal.begin() as db:
        teacher = db.query(User).filter_by(role=Role.teacher).one()
        course = Course(number="CS-STAGED", name="分阶段路线测试")
        db.add(course)
        db.flush()
        offering = CourseOffering(
            course_id=course.id, teacher_id=teacher.id, year=2026, term=1,
            status=OfferingStatus.active,
        )
        db.add(offering)
        db.flush()
        syllabus = CourseResource(
            offering_id=offering.id, uploader_id=teacher.id, title="课程大纲",
            resource_type="syllabus", original_name="outline.docx", object_key="test/outline.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size=100, sha256="1" * 64, processing_status=ProcessingStatus.ready, chunk_count=2,
        )
        textbook = CourseResource(
            offering_id=offering.id, uploader_id=teacher.id, title="课程教材",
            resource_type="textbook", original_name="book.pdf", object_key="test/book.pdf",
            mime_type="application/pdf", size=100, sha256="2" * 64,
            processing_status=ProcessingStatus.ready, chunk_count=2,
        )
        db.add_all([syllabus, textbook])
        db.flush()
        outline_rows = [
            ResourceChunk(
                resource_id=syllabus.id, offering_id=offering.id, position=index,
                block_type="heading", heading_path=name, text=f"大纲章节：{name}",
                token_count=10, content_hash=f"{index + 10:064x}",
            )
            for index, name in enumerate(["程序结构", "函数"])
        ]
        support_rows = [
            ResourceChunk(
                resource_id=textbook.id, offering_id=offering.id, position=index,
                block_type="paragraph", heading_path=name, text=text,
                token_count=20, content_hash=f"{index + 20:064x}",
            )
            for index, (name, text) in enumerate([
                ("程序结构", "教材私有内容：顺序、选择和循环结构。"),
                ("函数", "教材私有内容：函数声明、参数与返回值。"),
            ])
        ]
        db.add_all([*outline_rows, *support_rows])
        db.flush()
        offering_id = offering.id
        resource_ids = [syllabus.id, textbook.id]
        outline_ids = [row.id for row in outline_rows]

    with SessionLocal() as db:
        chunks, strategy = workflows._course_map_materials(db, offering_id, resource_ids)

    prompts: list[dict] = []

    def fake_completion(schema, *, user_prompt, **_kwargs):
        payload = json.loads(user_prompt)
        prompts.append(payload)
        metadata = {"model": "fake", "latency_ms": 1,
                    "token_usage": {"prompt": 1, "completion": 1, "total": 2}}
        if schema is CourseChapterPlan:
            assert "教材私有内容" not in user_prompt
            return CourseChapterPlan.model_validate({
                "title": "程序设计知识路线",
                "chapters": [
                    {"chapter_key": "c1", "name": "程序结构", "summary": "掌握控制结构",
                     "position": 1, "syllabus_chunk_ids": [outline_ids[0]]},
                    {"chapter_key": "c2", "name": "函数", "summary": "掌握函数使用",
                     "position": 2, "syllabus_chunk_ids": [outline_ids[1]]},
                ],
            }), metadata
        assert schema is ChapterKnowledgeBatch
        points = []
        for chapter in payload["chapters"]:
            evidence = payload["supporting_chunks"][chapter["chapter_key"]]
            chunk_ids = [item["chunk_id"] for item in evidence[:1]]
            points.extend([
                {"chapter_key": chapter["chapter_key"], "name": f"{chapter['name']}概念",
                 "summary": "理解核心概念", "evidence_chunk_ids": chunk_ids},
                {"chapter_key": chapter["chapter_key"], "name": f"{chapter['name']}应用",
                 "summary": "能够解决问题", "evidence_chunk_ids": chunk_ids},
            ])
        return ChapterKnowledgeBatch.model_validate({"knowledge_points": points}), metadata

    monkeypatch.setattr(workflows, "structured_completion", fake_completion)
    draft, metadata = workflows._model_course_map({
        "offering_id": offering_id,
        "input_data": {"resource_ids": resource_ids},
        "tool_results": {"course_map_chunks": chunks, "course_map_strategy": strategy},
    })

    contains = [edge for edge in draft["edges"] if edge["relation_type"] == "contains"]
    assert [node["name"] for node in draft["nodes"] if node["node_key"].startswith("chapter-")] == [
        "程序结构", "函数",
    ]
    assert len(contains) == 4
    assert len(prompts) == 2
    assert metadata["generation_mode"] == "staged-model"
    assert metadata["model_call_count"] == 2
    assert "章节结构来自教学大纲" in draft["summary"]
    assert "教材" in draft["summary"]
