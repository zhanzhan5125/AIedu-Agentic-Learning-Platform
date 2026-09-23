from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.responses import ok
from app.core.config import get_settings
from app.db import get_db
from app.dependencies import current_user, require_roles
from app.models import (AIJob, AgentRun, Assignment, CourseOffering, Enrollment, JobStatus,
                        OutboxEvent, Role, Submission, SubmissionStatus, User)
from app.schemas import AIJobCreate
from app.integrations.ai_provider import chat_completion, embedding_probe, provider_status
from app.integrations.runtime_cache import runtime_cache
from app.ai.workflows import agent_identity

router = APIRouter(tags=["AI 任务"])


class ChatProbeRequest(BaseModel):
    prompt: str = Field(default="只回复：AIedu 连接成功", min_length=1, max_length=500)


class EmbeddingProbeRequest(BaseModel):
    text: str = Field(default="AIedu 课程资料向量化测试", min_length=1, max_length=2000)


def _provider_error(exc: Exception) -> AppError:
    message = str(exc).strip() or exc.__class__.__name__
    return AppError(502, f"AI 服务调用失败：{message[:800]}")


@router.get("/ai/provider/status")
def ai_provider_status(request: Request,
                       _: User = Depends(require_roles(Role.teacher, Role.manager))):
    data = provider_status()
    data["business_endpoints"] = {
        "grading": "/api/v1/ai/grading-jobs",
        "assignment_summary": "/api/v1/ai/summary-jobs",
        "question_generation": "/api/v1/ai/question-jobs",
        "course_chat": "/api/v1/conversations/{conversation_id}/ask",
        "assignment_draft": "/api/v1/teacher/offerings/{offering_id}/assignment-drafts",
        "personal_practice": "/api/v1/student/offerings/{offering_id}/practice-jobs",
        "resource_reindex": "/api/v1/resources/{resource_id}/reindex",
        "job_status": "/api/v1/jobs/{job_id}",
        "agent_run": "/api/v1/agent-runs/{run_id}",
    }
    return ok(data, request.state.request_id)


@router.post("/ai/provider/test-chat")
def test_chat_provider(payload: ChatProbeRequest, request: Request,
                       user: User = Depends(require_roles(Role.teacher, Role.manager))):
    if not runtime_cache.allow("ai-provider-chat-test", user.id, 5, 60):
        raise AppError(429, "AI 连通性测试过于频繁，请稍后再试")
    try:
        result = chat_completion(payload.prompt)
    except Exception as exc:
        raise _provider_error(exc)
    return ok(result, request.state.request_id)


@router.post("/ai/provider/test-embedding")
def test_embedding_provider(payload: EmbeddingProbeRequest, request: Request,
                            user: User = Depends(require_roles(Role.teacher, Role.manager))):
    if not runtime_cache.allow("ai-provider-embedding-test", user.id, 5, 60):
        raise AppError(429, "Embedding 连通性测试过于频繁，请稍后再试")
    try:
        result = embedding_probe(payload.text)
    except Exception as exc:
        raise _provider_error(exc)
    return ok(result, request.state.request_id)


def enqueue(kind: str, resource_type: str, payload: AIJobCreate, user: User, db: Session) -> AIJob:
    existing = db.scalar(select(AIJob).where(AIJob.idempotency_key == payload.idempotency_key))
    if existing:
        if existing.owner_id != user.id or existing.kind != kind:
            raise Conflict("幂等键已被其他任务使用")
        return existing
    agent_name, task_type = agent_identity(kind)
    run = AgentRun(kind=kind, agent_name=agent_name, task_type=task_type,
                   owner_id=user.id, resource_type=resource_type,
                   resource_id=payload.resource_id, status=JobStatus.queued,
                   graph_version="four-agent-v1", prompt_version="four-agent-prompts-v1",
                   model=get_settings().llm_model)
    db.add(run)
    db.flush()
    job = AIJob(
        kind=kind,
        owner_id=user.id,
        resource_type=resource_type,
        resource_id=payload.resource_id,
        input_data={"prompt": payload.prompt},
        idempotency_key=payload.idempotency_key,
        agent_run_id=run.id,
    )
    db.add(job)
    db.flush()
    db.add(OutboxEvent(
        topic=get_settings().rocketmq_topic, tag=kind, aggregate_id=str(job.id),
        payload={"event_type": "ai.job", "job_id": job.id}
    ))
    # 由各接口在相关业务状态写入后统一提交，保证任务、Outbox 和资源状态原子一致。
    return job


def require_resource_access(kind: str, resource_id: int, user: User, db: Session) -> None:
    if kind == "grading.single":
        allowed = db.scalar(select(Submission.id).join(Assignment).join(CourseOffering).where(
            Submission.id == resource_id, CourseOffering.teacher_id == user.id))
    elif kind == "assignment.summary":
        allowed = db.scalar(select(Assignment.id).join(CourseOffering).where(
            Assignment.id == resource_id, CourseOffering.teacher_id == user.id))
    elif user.role == Role.teacher:
        allowed = db.scalar(select(CourseOffering.id).where(
            CourseOffering.id == resource_id, CourseOffering.teacher_id == user.id))
    else:
        allowed = db.scalar(select(Enrollment.id).join(CourseOffering).where(
            CourseOffering.id == resource_id, Enrollment.student_id == user.id))
    if not allowed:
        raise Forbidden("无权对该资源创建 AI 任务")


@router.post("/ai/grading-jobs", status_code=status.HTTP_202_ACCEPTED)
def grading_job(payload: AIJobCreate, request: Request, user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    require_resource_access("grading.single", payload.resource_id, user, db)
    submission = db.get(Submission, payload.resource_id)
    if submission.status not in (SubmissionStatus.submitted, SubmissionStatus.needs_review):
        raise Conflict("只有已提交或待教师确认的作业可以发起 AI 辅助批阅")
    job = enqueue("grading.single", "submission", payload, user, db)
    if job.status in (JobStatus.queued, JobStatus.running):
        submission.status = SubmissionStatus.ai_grading
        submission.review_reason = None
    db.commit()
    db.refresh(job)
    return ok({"job_id": job.id, "agent_run_id": job.agent_run_id,
               "status": job.status.value}, request.state.request_id)


@router.post("/ai/summary-jobs", status_code=status.HTTP_202_ACCEPTED)
def summary_job(payload: AIJobCreate, request: Request, user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    require_resource_access("assignment.summary", payload.resource_id, user, db)
    job = enqueue("assignment.summary", "assignment", payload, user, db)
    db.commit()
    db.refresh(job)
    return ok({"job_id": job.id, "status": job.status.value}, request.state.request_id)


@router.post("/ai/question-jobs", status_code=status.HTTP_202_ACCEPTED)
def question_job(payload: AIJobCreate, request: Request, user: User = Depends(require_roles(Role.teacher, Role.student)), db: Session = Depends(get_db)):
    require_resource_access("question.generate", payload.resource_id, user, db)
    job = enqueue("question.generate", "course", payload, user, db)
    db.commit()
    db.refresh(job)
    return ok({"job_id": job.id, "status": job.status.value}, request.state.request_id)


@router.post("/ai/chat", status_code=status.HTTP_202_ACCEPTED)
def chat_job(payload: AIJobCreate, request: Request, user: User = Depends(require_roles(Role.teacher, Role.student)), db: Session = Depends(get_db)):
    require_resource_access("rag.chat", payload.resource_id, user, db)
    job = enqueue("rag.chat", "course", payload, user, db)
    db.commit()
    db.refresh(job)
    return ok({"job_id": job.id, "status": job.status.value}, request.state.request_id)


@router.get("/jobs/{job_id}")
def get_job(job_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = db.scalar(select(AIJob).where(AIJob.id == job_id, AIJob.owner_id == user.id))
    if job is None:
        raise NotFound("任务不存在")
    return ok({"id": job.id, "kind": job.kind, "status": job.status.value, "progress": job.progress,
               "agent_run_id": job.agent_run_id,
               "result": job.result_data, "error": job.error_message}, request.state.request_id)
