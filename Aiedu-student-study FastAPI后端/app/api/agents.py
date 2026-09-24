from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.responses import ok
from app.db import get_db
from app.dependencies import current_user, require_roles
from app.models import (
    AIJob,
    AgentFeedback,
    AgentRun,
    AgentRunStep,
    Assignment,
    CourseMapEdge,
    CourseMapNode,
    CourseMapVersion,
    CourseOffering,
    Enrollment,
    JobStatus,
    KnowledgePoint,
    OutboxEvent,
    PracticeSession,
    Role,
    User,
)
from app.schemas import (AgentFeedbackCreate, AssignmentDraftRequest, CourseMapDraftRequest,
                         PracticeJobRequest, PracticeSubmitRequest)
from app.ai.workflows import agent_identity
from app.services.access import offering_for_user
from app.services.learning import profile_view
from app.integrations.runtime_cache import runtime_cache
from app.core.errors import AppError

router = APIRouter(tags=["多智能体协作"])


def queue_agent(db: Session, *, kind: str, resource_type: str, resource_id: int,
                owner: User, idempotency_key: str, input_data: dict) -> tuple[AIJob, AgentRun]:
    existing = db.scalar(select(AIJob).where(AIJob.idempotency_key == idempotency_key))
    if existing:
        if existing.owner_id != owner.id or existing.kind != kind:
            raise Conflict("幂等键已被其他任务使用")
        run = db.get(AgentRun, existing.agent_run_id) if existing.agent_run_id else None
        if run is None:
            raise Conflict("任务审计记录缺失")
        return existing, run
    agent_name, task_type = agent_identity(kind)
    run = AgentRun(kind=kind, agent_name=agent_name, task_type=task_type,
                   owner_id=owner.id, resource_type=resource_type,
                   resource_id=resource_id, status=JobStatus.queued,
                   graph_version="four-agent-v1", prompt_version="four-agent-prompts-v1",
                   model=get_settings().llm_model)
    db.add(run)
    db.flush()
    job = AIJob(kind=kind, owner_id=owner.id, resource_type=resource_type,
                resource_id=resource_id, status=JobStatus.queued, input_data=input_data,
                idempotency_key=idempotency_key, agent_run_id=run.id)
    db.add(job)
    db.flush()
    db.add(OutboxEvent(topic=get_settings().rocketmq_topic, tag=kind,
                       aggregate_id=str(job.id), payload={"event_type": "ai.job", "job_id": job.id}))
    return job, run


@router.post("/teacher/offerings/{offering_id}/assignment-drafts", status_code=status.HTTP_202_ACCEPTED)
def generate_assignment_draft(offering_id: int, payload: AssignmentDraftRequest, request: Request,
                              user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    if not runtime_cache.allow("question-generate", user.id, 10, 60):
        raise AppError(429, "出题任务过于频繁，请稍后再试")
    offering = offering_for_user(db, offering_id, user)
    ids = set(payload.knowledge_point_ids)
    selected_node_ids = set(payload.course_map_node_ids)
    selected_chapter_names: list[str] = []
    if selected_node_ids:
        selected_nodes = db.scalars(select(CourseMapNode).join(
            CourseMapVersion, CourseMapVersion.id == CourseMapNode.version_id
        ).where(
            CourseMapNode.id.in_(selected_node_ids),
            CourseMapVersion.offering_id == offering_id,
            CourseMapVersion.status == "published",
        )).all()
        if {node.id for node in selected_nodes} != selected_node_ids:
            raise Conflict("包含未发布或不属于该教学班的课程路线章节")
        version_ids = {node.version_id for node in selected_nodes}
        if len(version_ids) != 1:
            raise Conflict("所选章节必须来自同一个已发布课程路线版本")
        version_id = next(iter(version_ids))
        all_nodes = db.scalars(select(CourseMapNode).where(
            CourseMapNode.version_id == version_id
        )).all()
        nodes_by_id = {node.id: node for node in all_nodes}
        children: dict[int, set[int]] = {}
        for edge in db.scalars(select(CourseMapEdge).where(
            CourseMapEdge.version_id == version_id,
            CourseMapEdge.relation_type == "contains",
        )).all():
            children.setdefault(edge.source_node_id, set()).add(edge.target_node_id)
        expanded_node_ids: set[int] = set()
        for node in selected_nodes:
            selected_chapter_names.append(node.name)
            pending = list(children.get(node.id, set()))
            descendants: set[int] = set()
            while pending:
                current = pending.pop()
                if current in descendants:
                    continue
                descendants.add(current)
                pending.extend(children.get(current, set()))
            expanded_node_ids.update(descendants or {node.id})
        ids.update(nodes_by_id[node_id].knowledge_point_id for node_id in expanded_node_ids
                   if node_id in nodes_by_id and nodes_by_id[node_id].knowledge_point_id)
    if ids:
        valid = set(db.scalars(select(KnowledgePoint.id).where(
            KnowledgePoint.course_id == offering.course_id, KnowledgePoint.id.in_(ids)
        )).all())
        if valid != ids:
            raise Conflict("包含不属于该课程的知识点")
    input_data = payload.model_dump(exclude={"idempotency_key"})
    input_data["knowledge_point_ids"] = sorted(ids)
    input_data["selected_chapter_names"] = selected_chapter_names
    if ids:
        input_data["selected_knowledge_point_names"] = list(db.scalars(select(KnowledgePoint.name).where(
            KnowledgePoint.id.in_(ids)
        )).all())
    job, run = queue_agent(
        db, kind="assignment.draft", resource_type="offering", resource_id=offering_id,
        owner=user, idempotency_key=payload.idempotency_key,
        input_data=input_data,
    )
    db.commit()
    return ok({"job_id": job.id, "agent_run_id": run.id, "status": job.status.value}, request.state.request_id)


@router.post("/teacher/offerings/{offering_id}/course-map-drafts", status_code=status.HTTP_202_ACCEPTED)
def generate_course_map_draft(offering_id: int, payload: CourseMapDraftRequest, request: Request,
                              user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    offering_for_user(db, offering_id, user)
    if payload.resource_ids:
        from app.models import CourseResource, ProcessingStatus
        valid = set(db.scalars(select(CourseResource.id).where(
            CourseResource.offering_id == offering_id,
            CourseResource.id.in_(payload.resource_ids),
            CourseResource.processing_status == ProcessingStatus.ready,
        )).all())
        if valid != set(payload.resource_ids):
            raise Conflict("包含未完成索引或不属于该教学班的资料")
    job, run = queue_agent(
        db, kind="course_map.generate", resource_type="offering", resource_id=offering_id,
        owner=user, idempotency_key=payload.idempotency_key,
        input_data=payload.model_dump(exclude={"idempotency_key"}),
    )
    db.commit()
    return ok({"job_id": job.id, "agent_run_id": run.id, "status": job.status.value},
              request.state.request_id)


def _practice_job(offering_id: int, assignment_id: int | None, payload: PracticeJobRequest,
                  request: Request, user: User, db: Session):
    offering = offering_for_user(db, offering_id, user)
    ids = list(payload.knowledge_point_ids)
    practice_mode = "selected"
    if not ids:
        profile = profile_view(db, user.id, offering_id)
        weak = [item for item in profile["knowledge_points"] if item["state"] == "weak"]
        observed = [item for item in profile["knowledge_points"] if item["state"] != "unobserved"]
        if weak:
            selected, practice_mode = weak, "weak_point_review"
        elif observed:
            selected, practice_mode = profile["knowledge_points"], "comprehensive_review"
        else:
            selected, practice_mode = profile["knowledge_points"], "course_baseline"
        ids = [item["id"] for item in selected]
        selected_names = [item["name"] for item in selected]
    elif set(ids) != set(db.scalars(select(KnowledgePoint.id).where(
        KnowledgePoint.course_id == offering.course_id, KnowledgePoint.id.in_(ids)
    )).all()):
        raise Conflict("包含不属于该课程的知识点")
    else:
        selected_names = list(db.scalars(select(KnowledgePoint.name).where(
            KnowledgePoint.course_id == offering.course_id, KnowledgePoint.id.in_(ids))).all())
    if not ids:
        raise Conflict("课程尚未配置知识点，无法生成个性化练习")
    job, run = queue_agent(
        db, kind="practice.generate", resource_type="assignment" if assignment_id else "offering",
        resource_id=assignment_id or offering_id, owner=user, idempotency_key=payload.idempotency_key,
        input_data={**payload.model_dump(exclude={"idempotency_key"}),
                    "knowledge_point_ids": ids, "offering_id": offering_id,
                    "assignment_id": assignment_id, "practice_mode": practice_mode,
                    "keywords": selected_names},
    )
    db.commit()
    return ok({"job_id": job.id, "agent_run_id": run.id, "status": job.status.value}, request.state.request_id)


@router.post("/student/offerings/{offering_id}/practice-jobs", status_code=status.HTTP_202_ACCEPTED)
def offering_practice(offering_id: int, payload: PracticeJobRequest, request: Request,
                      user: User = Depends(require_roles(Role.student)), db: Session = Depends(get_db)):
    return _practice_job(offering_id, None, payload, request, user, db)


@router.get("/student/offerings/{offering_id}/practice-runs/latest")
def latest_offering_practice(offering_id: int, request: Request,
                             user: User = Depends(require_roles(Role.student)),
                             db: Session = Depends(get_db)):
    offering_for_user(db, offering_id, user)
    run = db.scalar(select(AgentRun).where(
        AgentRun.owner_id == user.id,
        AgentRun.kind == "practice.generate",
        AgentRun.resource_type == "offering",
        AgentRun.resource_id == offering_id,
    ).order_by(AgentRun.created_at.desc(), AgentRun.id.desc()))
    if run is None:
        return ok(None, request.state.request_id)
    return ok({
        "id": run.id,
        "status": run.status.value,
        "result": run.result,
        "error": run.error,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }, request.state.request_id)


def _practice_session_view(db: Session, session: PracticeSession, *, detail: bool = False) -> dict:
    completed = session.status == "completed"
    answers = {
        int(item.get("question_index")): item.get("content", "")
        for item in (session.answers or [])
    }
    feedback_items = {
        int(item.get("question_index")): item
        for item in ((session.feedback or {}).get("items") or [])
    }
    questions = []
    if detail:
        for index, source in enumerate(session.questions or []):
            question = {
                "question_index": index,
                "kind": source.get("kind", "short_answer"),
                "prompt": source.get("prompt", ""),
                "score": int(source.get("score") or 10),
                "difficulty": int(source.get("difficulty") or 2),
                "knowledge_point_ids": source.get("knowledge_point_ids") or [],
                "student_answer": answers.get(index, ""),
                "feedback": feedback_items.get(index) if completed else None,
            }
            # 参考答案与评分点只在提交并完成反馈后开放，避免练习前直接泄题。
            if completed:
                question["reference_answer"] = source.get("reference_answer", "")
                question["rubric"] = source.get("rubric") or []
            questions.append(question)
    assignment = db.get(Assignment, session.assignment_id) if session.assignment_id else None
    return {
        "id": session.id,
        "offering_id": session.offering_id,
        "assignment_id": session.assignment_id,
        "assignment_title": assignment.title if assignment else None,
        "status": session.status,
        "rationale": session.rationale,
        "question_count": len(session.questions or []),
        "questions": questions,
        "score": session.score,
        "total_score": session.total_score,
        "summary": (session.feedback or {}).get("summary") if completed else None,
        "agent_run_id": session.agent_run_id,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "completed_at": session.completed_at,
    }


@router.get("/student/offerings/{offering_id}/practice-sessions")
def list_practice_sessions(offering_id: int, request: Request,
                           page: int = Query(default=1, ge=1),
                           page_size: int = Query(default=20, ge=1, le=100),
                           user: User = Depends(require_roles(Role.student)),
                           db: Session = Depends(get_db)):
    offering_for_user(db, offering_id, user)
    filters = (
        PracticeSession.student_id == user.id,
        PracticeSession.offering_id == offering_id,
    )
    total = db.scalar(select(func.count(PracticeSession.id)).where(*filters)) or 0
    rows = db.scalars(select(PracticeSession).where(*filters).order_by(
        PracticeSession.created_at.desc(), PracticeSession.id.desc()
    ).offset((page - 1) * page_size).limit(page_size)).all()
    return ok({
        "items": [_practice_session_view(db, row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }, request.state.request_id)


@router.get("/student/practice-sessions/{session_id}")
def get_practice_session(session_id: int, request: Request,
                         user: User = Depends(require_roles(Role.student)),
                         db: Session = Depends(get_db)):
    session = db.get(PracticeSession, session_id)
    if session is None or session.student_id != user.id:
        raise NotFound("个人练习不存在")
    offering_for_user(db, session.offering_id, user)
    return ok(_practice_session_view(db, session, detail=True), request.state.request_id)


@router.post("/student/practice-sessions/{session_id}/submit", status_code=status.HTTP_202_ACCEPTED)
def submit_practice_session(session_id: int, payload: PracticeSubmitRequest, request: Request,
                            user: User = Depends(require_roles(Role.student)),
                            db: Session = Depends(get_db)):
    session = db.get(PracticeSession, session_id)
    if session is None or session.student_id != user.id:
        raise NotFound("个人练习不存在")
    offering_for_user(db, session.offering_id, user)
    if session.status == "completed":
        raise Conflict("这次练习已经完成")
    if session.status == "feedback_pending":
        raise Conflict("练习反馈正在生成，请稍候")
    expected_indices = set(range(len(session.questions or [])))
    submitted_indices = [item.question_index for item in payload.answers]
    if len(submitted_indices) != len(set(submitted_indices)):
        raise Conflict("同一道练习题不能重复提交")
    if set(submitted_indices) != expected_indices:
        raise Conflict("请完成全部练习题后再提交")
    session.answers = [item.model_dump() for item in sorted(
        payload.answers, key=lambda value: value.question_index
    )]
    session.status = "feedback_pending"
    job, run = queue_agent(
        db,
        kind="practice.feedback",
        resource_type="practice_session",
        resource_id=session.id,
        owner=user,
        idempotency_key=payload.idempotency_key,
        input_data={"offering_id": session.offering_id, "practice_session_id": session.id},
    )
    db.commit()
    return ok({
        "practice_session_id": session.id,
        "job_id": job.id,
        "agent_run_id": run.id,
        "status": job.status.value,
    }, request.state.request_id)


@router.post("/student/assignments/{assignment_id}/practice-jobs", status_code=status.HTTP_202_ACCEPTED)
def assignment_practice(assignment_id: int, payload: PracticeJobRequest, request: Request,
                        user: User = Depends(require_roles(Role.student)), db: Session = Depends(get_db)):
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise NotFound("作业不存在")
    return _practice_job(assignment.offering_id, assignment_id, payload, request, user, db)


@router.get("/agent-runs/{run_id}")
def get_agent_run(run_id: int, request: Request, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    run = db.get(AgentRun, run_id)
    if run is None or (run.owner_id != user.id and user.role != Role.manager):
        raise NotFound("智能体运行记录不存在")
    job = db.scalar(select(AIJob).where(AIJob.agent_run_id == run.id))
    return ok({"id": run.id, "kind": run.kind, "agent_name": run.agent_name,
               "task_type": run.task_type, "parent_run_id": run.parent_run_id,
               "resource_type": run.resource_type,
               "resource_id": run.resource_id, "status": run.status.value,
               "graph_version": run.graph_version, "prompt_version": run.prompt_version,
               "model": run.model, "latency_ms": run.latency_ms,
               "token_usage": run.token_usage, "plan": run.plan,
               "reflection_count": run.reflection_count,
               "result": run.result, "error": run.error,
               "attempts": job.attempts if job else 0,
               "max_attempts": job.max_attempts if job else 0,
               "last_error": job.error_message if job else None,
               "created_at": run.created_at, "updated_at": run.updated_at}, request.state.request_id)


@router.get("/agent-runs/{run_id}/steps")
def get_agent_steps(run_id: int, request: Request, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    run = db.get(AgentRun, run_id)
    if run is None or (run.owner_id != user.id and user.role != Role.manager):
        raise NotFound("智能体运行记录不存在")
    rows = db.scalars(select(AgentRunStep).where(AgentRunStep.run_id == run_id)
                      .order_by(AgentRunStep.position)).all()
    return ok([{"position": row.position, "node_name": row.node_name,
                "agent_name": row.agent_name, "step_type": row.step_type,
                "tool_name": row.tool_name, "input_digest": row.input_digest,
                "output_summary": row.output_summary, "status": row.status,
                "duration_ms": row.duration_ms} for row in rows], request.state.request_id)


@router.post("/agent-runs/{run_id}/feedback", status_code=status.HTTP_201_CREATED)
def create_agent_feedback(run_id: int, payload: AgentFeedbackCreate, request: Request,
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = db.get(AgentRun, run_id)
    if run is None or run.owner_id != user.id:
        raise NotFound("智能体运行记录不存在")
    feedback = AgentFeedback(
        run_id=run.id, user_id=user.id, feedback_type=payload.feedback_type,
        before_value=payload.before_value, after_value=payload.after_value,
        comment=payload.comment,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return ok({"id": feedback.id, "feedback_type": feedback.feedback_type},
              request.state.request_id)
