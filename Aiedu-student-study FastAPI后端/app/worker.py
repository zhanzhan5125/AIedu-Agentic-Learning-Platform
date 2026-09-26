from __future__ import annotations

import time
import threading
import logging
import json
import hashlib
from datetime import datetime
from time import perf_counter

from sqlalchemy import func, select, update

from app.ai.tracing import persist_execution_trace
from app.ai.workflows import run_workflow
from app.core.config import get_settings
from app.db import SessionLocal
from app.integrations.rocketmq import rocketmq
from app.models import (AIJob, AgentRun, AgentRunStep, Answer, Assignment, AssignmentInsightSnapshot, AssignmentQuestion,
                        AssignmentStatus, ConsumerInbox, CourseResource, Enrollment,
                        JobStatus, Notification, OutboxEvent, PracticeSession, ProcessingStatus,
                        Question, QuestionKnowledgePoint, ScheduledNotification, Submission,
                        SubmissionStatus, ResourceChunk, CourseMapVersion, CourseMapNode,
                        CourseMapEdge, CourseMapEvidence, CourseOffering)
from app.services.submissions import auto_submit_expired_drafts
from app.integrations.object_storage import object_storage
from app.integrations.rag import chunk_blocks, delete_resource_vectors, extract_blocks, index_resource
from app.integrations.runtime_cache import runtime_cache
from app.integrations.realtime import publish_message
from app.services.insights import assignment_insights
from app.services.learning import refresh_class_mastery, refresh_student_mastery, upsert_evidence


logger = logging.getLogger(__name__)


def maintain_deadlines() -> int:
    with SessionLocal() as db:
        count = auto_submit_expired_drafts(db)
    if count:
        logger.info("Auto-submitted %s saved assignment snapshots at deadline", count)
    return count


def deliver_scheduled_notifications() -> int:
    delivered = 0
    realtime_deliveries: list[tuple[list[int], dict]] = []
    with SessionLocal() as db:
        rows = db.scalars(select(ScheduledNotification).where(
            ScheduledNotification.sent_at.is_(None), ScheduledNotification.scheduled_at <= datetime.now()
        ).limit(100)).all()
        for row in rows:
            claimed = db.execute(
                update(ScheduledNotification)
                .where(ScheduledNotification.id == row.id,
                       ScheduledNotification.sent_at.is_(None))
                .values(sent_at=datetime.now())
            )
            if claimed.rowcount == 0:
                continue
            submitted = select(Submission.student_id).where(
                Submission.assignment_id == row.assignment_id,
                Submission.status.notin_([SubmissionStatus.not_started, SubmissionStatus.draft]),
            )
            student_ids = db.scalars(select(Enrollment.student_id).where(
                Enrollment.offering_id == row.offering_id,
                Enrollment.student_id.notin_(submitted),
            )).all()
            hours = row.payload.get("hours", 0)
            title = "作业截止提醒"
            body = f"{row.payload.get('title', '作业')} 将在 {hours} 小时后截止。"
            db.add_all([Notification(user_id=student_id, offering_id=row.offering_id,
                                     kind=row.kind,
                                     title=title, body=body)
                        for student_id in student_ids])
            realtime_deliveries.append((list(student_ids), {
                "event_type": "notification", "offering_id": row.offering_id,
                "title": title, "body": body,
            }))
            delivered += len(student_ids)
        db.commit()
    for student_ids, payload in realtime_deliveries:
        publish_message(student_ids, payload)
    return delivered


def publish_outbox() -> int:
    published = 0
    with SessionLocal() as db:
        events = db.scalars(select(OutboxEvent).where(OutboxEvent.published_at.is_(None))
                            .order_by(OutboxEvent.id).limit(100)).all()
        for event in events:
            try:
                rocketmq.publish(event.topic, event.tag, event.aggregate_id,
                                 {**event.payload, "_event_id": event.id})
                event.published_at = datetime.now()
                published += 1
            except Exception as exc:
                event.attempts += 1
                logger.warning(
                    "Outbox publish failed for event %s (attempt %s): %s",
                    event.id,
                    event.attempts,
                    exc,
                )
        db.commit()
    return published


def _process_job(payload: dict) -> None:
    job_id = int(payload["job_id"])
    with SessionLocal() as db:
        job = db.get(AIJob, job_id)
        if job is None or job.status in {JobStatus.succeeded, JobStatus.cancelled}:
            return
        job.status = JobStatus.running
        run = db.get(AgentRun, job.agent_run_id) if job.agent_run_id else None
        if run:
            run.status = JobStatus.running
        job.progress = 10
        db.commit()
        started = perf_counter()
        try:
            output = run_workflow(
                job.kind, job.resource_id, job.input_data.get("prompt"),
                job.input_data, owner_id=job.owner_id,
            )
            if job.kind == "assignment.draft":
                assignment = Assignment(
                    offering_id=job.resource_id,
                    title=f"AI 生成作业草稿 {datetime.now():%m-%d %H:%M}",
                    status=AssignmentStatus.draft,
                    origin="agent",
                    agent_run_id=run.id if run else None,
                )
                db.add(assignment)
                db.flush()
                total_score = 0
                for position, item in enumerate(output["result"].get("questions", []), 1):
                    question = Question(
                        kind=item.get("kind", "short_answer"), prompt=item["prompt"],
                        reference_answer=item.get("reference_answer"),
                        score=int(item.get("score", 10)), difficulty=int(item.get("difficulty", 2)),
                    )
                    db.add(question)
                    db.flush()
                    db.add(AssignmentQuestion(assignment_id=assignment.id, question_id=question.id,
                                              position=position))
                    for knowledge_id in set(item.get("knowledge_point_ids", [])):
                        db.add(QuestionKnowledgePoint(question_id=question.id,
                                                      knowledge_point_id=int(knowledge_id), weight=100))
                    total_score += question.score
                assignment.total_score = total_score
                output["result"]["assignment_id"] = assignment.id
            elif job.kind == "practice.generate":
                session = PracticeSession(
                    student_id=job.owner_id,
                    offering_id=int(job.input_data["offering_id"]),
                    assignment_id=job.input_data.get("assignment_id"),
                    status="ready",
                    rationale=output["result"].get("reason", "根据个人学习画像生成"),
                    questions=output["result"].get("questions", []),
                    agent_run_id=run.id if run else None,
                )
                db.add(session)
                db.flush()
                output["result"]["practice_session_id"] = session.id
            elif job.kind == "practice.feedback":
                session = db.get(PracticeSession, job.resource_id)
                if session is None or session.student_id != job.owner_id:
                    raise ValueError("个人练习不存在或不属于当前学生")
                result = output["result"]
                session.feedback = result
                session.score = int(result.get("total_score") or 0)
                session.total_score = int(result.get("max_score") or 0)
                session.status = "completed"
                session.completed_at = datetime.now()

                # 同一场练习中，同一知识点可能出现在多道题里；先按题目得分比聚合，
                # 再写入一条稳定证据，避免题数多的知识点被重复加权。
                scores_by_point: dict[int, list[int]] = {}
                trustworthy_model_result = str(result.get("mode") or "").startswith("model")
                for item in result.get("items", []):
                    maximum = max(1, int(item.get("max_score") or 1))
                    normalized_score = round(int(item.get("score") or 0) / maximum * 100)
                    if not trustworthy_model_result and not item.get("is_correct"):
                        continue
                    for knowledge_id in set(item.get("knowledge_point_ids") or []):
                        scores_by_point.setdefault(int(knowledge_id), []).append(normalized_score)
                for knowledge_id, scores in scores_by_point.items():
                    upsert_evidence(
                        db,
                        student_id=session.student_id,
                        offering_id=session.offering_id,
                        knowledge_point_id=knowledge_id,
                        source_type="practice",
                        source_id=session.id,
                        score=round(sum(scores) / len(scores)),
                        confidence=90 if trustworthy_model_result else 100,
                        agent_run_id=run.id if run else None,
                        observed_at=session.completed_at,
                    )
                refresh_student_mastery(db, session.student_id, session.offering_id)
                refresh_class_mastery(db, session.offering_id)
                output["result"]["practice_session_id"] = session.id
            elif job.kind == "course_map.generate":
                offering = db.get(CourseOffering, job.resource_id)
                if offering is None:
                    raise ValueError("教学班不存在")
                version_number = (db.scalar(select(func.max(CourseMapVersion.version)).where(
                    CourseMapVersion.course_id == offering.course_id
                )) or 0) + 1
                course_map = CourseMapVersion(
                    course_id=offering.course_id, offering_id=offering.id,
                    version=version_number, status="draft",
                    title=output["result"].get("title", "课程知识路线"),
                    summary=output["result"].get("summary"), created_by=job.owner_id,
                    agent_run_id=run.id if run else None,
                )
                db.add(course_map)
                db.flush()
                nodes: dict[str, CourseMapNode] = {}
                for item in output["result"].get("nodes", []):
                    node = CourseMapNode(
                        version_id=course_map.id, node_key=item["node_key"], name=item["name"],
                        description=item.get("description"), position=int(item.get("position", 0)),
                        confidence=int(item.get("confidence", 0)),
                    )
                    db.add(node)
                    db.flush()
                    nodes[item["node_key"]] = node
                    for chunk_id in set(item.get("evidence_chunk_ids", [])):
                        if db.get(ResourceChunk, int(chunk_id)):
                            db.add(CourseMapEvidence(node_id=node.id, chunk_id=int(chunk_id)))
                for item in output["result"].get("edges", []):
                    source = nodes.get(item["source_key"])
                    target = nodes.get(item["target_key"])
                    if source is None or target is None:
                        continue
                    edge = CourseMapEdge(
                        version_id=course_map.id, source_node_id=source.id, target_node_id=target.id,
                        relation_type=item["relation_type"], confidence=int(item.get("confidence", 0)),
                    )
                    db.add(edge)
                    db.flush()
                    for chunk_id in set(item.get("evidence_chunk_ids", [])):
                        if db.get(ResourceChunk, int(chunk_id)):
                            db.add(CourseMapEvidence(edge_id=edge.id, chunk_id=int(chunk_id)))
                output["result"]["course_map_version_id"] = course_map.id
            job.result_data = output["result"]
            job.status = JobStatus.succeeded
            job.progress = 100
            job.error_message = None
            if job.kind == "grading.single":
                submission = db.get(Submission, job.resource_id)
                if submission is not None:
                    grading_result = output["result"]
                    submission.ai_comment = json.dumps(grading_result, ensure_ascii=False)
                    submission.ai_graded_at = datetime.now()
                    submission.ai_confidence = int(grading_result.get("confidence") or 0)
                    validation_issues = output.get("validation", {}).get("issues") or []
                    submission.review_reason = (
                        grading_result.get("review_reason") or
                        ("AI 输出未通过完整评分校验：" + "；".join(validation_issues)[:400]
                         if validation_issues else "AI 批阅建议待教师确认")
                    )
                    answers = {item.id: item for item in db.scalars(select(Answer).where(
                        Answer.submission_id == submission.id
                    )).all()}
                    for item in grading_result.get("items", []):
                        answer = answers.get(int(item.get("answer_id", 0)))
                        if answer is None:
                            continue
                        answer.ai_comment = item.get("comment")
                        answer.ai_raw = item
                    # AI 结果始终是建议，默认必须由教师确认后才能成为最终成绩。
                    submission.status = SubmissionStatus.needs_review
            if run:
                run.status = JobStatus.succeeded
                persist_execution_trace(
                    db, run, output,
                    latency_ms=round((perf_counter() - started) * 1000),
                )
        except Exception as exc:
            job.attempts += 1
            job.error_message = str(exc)[:2000]
            if job.attempts < job.max_attempts:
                job.status = JobStatus.queued
                job.progress = 0
                if run:
                    run.status = JobStatus.queued
                # A failed RocketMQ message stays invisible for the full task
                # lease (30 minutes in development). Create a fresh durable
                # event and acknowledge the old one so transient model errors
                # retry promptly without shortening the lease for long jobs.
                db.add(OutboxEvent(
                    topic=get_settings().rocketmq_topic,
                    tag=job.kind,
                    aggregate_id=f"{job.id}:retry:{job.attempts}",
                    payload={
                        "event_type": "ai.job", "job_id": job.id,
                        "retry_attempt": job.attempts,
                    },
                ))
                db.commit()
                logger.warning(
                    "AI job %s queued for prompt retry %s/%s: %s",
                    job.id, job.attempts, job.max_attempts, exc,
                )
                return
            job.status = JobStatus.failed
            if run:
                run.status = JobStatus.failed
                run.error = str(exc)[:2000]
                run.latency_ms = round((perf_counter() - started) * 1000)
            if job.kind == "grading.single":
                submission = db.get(Submission, job.resource_id)
                if submission is not None:
                    submission.status = SubmissionStatus.needs_review
                    submission.review_reason = "AI 批阅失败，请教师直接批阅"
            if job.kind == "practice.feedback":
                session = db.get(PracticeSession, job.resource_id)
                if session is not None:
                    session.status = "feedback_failed"
        db.commit()


def process_job(payload: dict) -> None:
    job_id = int(payload["job_id"])
    with runtime_cache.lock(f"ai-job:{job_id}", ttl_seconds=300) as acquired:
        if acquired:
            _process_job(payload)


def _process_resource(payload: dict) -> None:
    resource_id = int(payload["resource_id"])
    with SessionLocal() as db:
        resource = db.get(CourseResource, resource_id)
        if resource is None:
            return
        if payload["event_type"] == "resource.delete":
            object_storage.delete(resource.object_key)
            delete_resource_vectors(resource.id)
            return
        # Upload and delete events are durable and may be consumed later or by
        # different workers.  A stale ingest event must never resurrect or
        # spend embedding quota on a resource that the teacher already deleted.
        if resource.deleted_at is not None or resource.processing_status == ProcessingStatus.deleted:
            logger.info("Skip indexing deleted resource %s", resource.id)
            return
        try:
            resource.processing_status = ProcessingStatus.parsing
            db.commit()
            content = object_storage.get(resource.object_key)
            blocks, page_count = extract_blocks(content, resource.mime_type)
            chunk_values = chunk_blocks(blocks)
            if not chunk_values:
                raise ValueError("资料未提取到可索引文本")
            resource.processing_status = ProcessingStatus.indexing
            db.commit()
            db.query(ResourceChunk).filter(ResourceChunk.resource_id == resource.id).delete()
            records: list[ResourceChunk] = []
            for position, item in enumerate(chunk_values):
                record = ResourceChunk(
                    resource_id=resource.id,
                    offering_id=resource.offering_id,
                    position=position,
                    block_type=item.get("block_type", "paragraph"),
                    heading_path=item.get("heading_path"),
                    page_number=item.get("page_number"),
                    slide_number=item.get("slide_number"),
                    text=item["text"],
                    token_count=int(item["token_count"]),
                    content_hash=hashlib.sha256(item["text"].encode()).hexdigest(),
                )
                db.add(record)
                records.append(record)
            db.flush()
            indexed = [{
                "id": row.id,
                "position": row.position,
                "block_type": row.block_type,
                "heading_path": row.heading_path,
                "page_number": row.page_number,
                "slide_number": row.slide_number,
                "text": row.text,
            } for row in records]
            chunk_count = index_resource(
                resource.id, resource.offering_id, resource.title,
                indexed_chunks=indexed, resource_type=resource.resource_type,
            )
            resource.processing_status = ProcessingStatus.ready
            resource.page_count = page_count
            resource.chunk_count = chunk_count
            resource.embedding_model = get_settings().embedding_model
            resource.indexed_at = datetime.now()
            resource.error_message = None
        except Exception as exc:
            # Parsing/indexing mutates chunks in the current transaction.  A
            # failed embedding or vector write must not commit a half-built
            # replacement and erase the last usable relational index.
            db.rollback()
            resource = db.get(CourseResource, resource_id)
            if resource is None:
                return
            logger.exception(
                "Resource %s failed while status=%s",
                resource.id, resource.processing_status.value,
            )
            resource.processing_status = ProcessingStatus.failed
            resource.error_message = str(exc)[:2000]
        db.commit()


def process_resource(payload: dict) -> None:
    resource_id = int(payload["resource_id"])
    with runtime_cache.lock(f"resource-index:{resource_id}", ttl_seconds=600) as acquired:
        if not acquired:
            # Let RocketMQ redeliver instead of acknowledging an event whose
            # work never ran.  This also protects delete events from being lost
            # while another worker is still indexing the same resource.
            raise RuntimeError(f"资料 {resource_id} 正由其他 Worker 处理，请稍后重试")
        _process_resource(payload)


def process_teaching_event(payload: dict) -> None:
    if payload.get("event_type") != "submission.graded":
        return
    with SessionLocal.begin() as db:
        submission = db.get(Submission, int(payload["submission_id"]))
        if submission is None:
            return
        assignment = db.get(Assignment, submission.assignment_id)
        version = (db.scalar(select(func.max(AssignmentInsightSnapshot.version)).where(
            AssignmentInsightSnapshot.assignment_id == assignment.id
        )) or 0) + 1
        db.add(AssignmentInsightSnapshot(assignment_id=assignment.id, version=version,
                                         data=assignment_insights(db, assignment),
                                         snapshot_at=datetime.now()))


def process_event(payload: dict) -> None:
    event_id = payload.get("_event_id")
    if event_id:
        with SessionLocal() as db:
            if db.scalar(select(ConsumerInbox.id).where(
                ConsumerInbox.event_id == int(event_id),
                ConsumerInbox.consumer_name == "aiedu-worker",
            )):
                return
    event_type = payload.get("event_type", "ai.job")
    if event_type == "ai.job" or "job_id" in payload:
        process_job(payload)
    elif event_type.startswith("resource."):
        process_resource(payload)
    elif event_type in {"assignment.published", "submission.graded"}:
        process_teaching_event(payload)
    # Teaching events are durable integration facts; local side effects are already committed.
    if event_id:
        with SessionLocal.begin() as db:
            db.add(ConsumerInbox(event_id=int(event_id), consumer_name="aiedu-worker"))


def run_local_once() -> int:
    """Development/CI execution path without a broker; still consumes the transactional outbox."""
    handled = 0
    with SessionLocal() as db:
        events = db.scalars(select(OutboxEvent).where(OutboxEvent.published_at.is_(None))
                            .order_by(OutboxEvent.id).limit(100)).all()
        payloads = [(event.id, {**event.payload, "_event_id": event.id}) for event in events]
    for event_id, payload in payloads:
        process_event(payload)
        with SessionLocal() as db:
            event = db.get(OutboxEvent, event_id)
            if event and event.published_at is None:
                event.published_at = datetime.now()
                db.commit()
        if payload.get("event_type", "ai.job") == "ai.job" or "job_id" in payload:
            handled += 1
    return handled


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = get_settings()
    if settings.enable_mq:
        def outbox_loop() -> None:
            while True:
                publish_outbox()
                maintain_deadlines()
                deliver_scheduled_notifications()
                time.sleep(1)

        threading.Thread(target=outbox_loop, name="outbox-publisher", daemon=True).start()
        rocketmq.consume_forever(process_event)
        return
    while True:
        run_local_once()
        maintain_deadlines()
        deliver_scheduled_notifications()
        time.sleep(2)


if __name__ == "__main__":
    run()
