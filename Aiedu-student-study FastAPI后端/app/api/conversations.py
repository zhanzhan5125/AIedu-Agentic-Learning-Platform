from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher
import hashlib
import re

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, NotFound
from app.core.responses import ok
from app.db import get_db
from app.dependencies import require_roles
from app.models import (AgentRun, Assignment, AssignmentQuestion,
                        AssignmentStatus, ChatMessage, Conversation, ConversationStatus,
                        Enrollment, JobStatus, MessageRole, MessageStatus, Question, Role, User)
from app.schemas import AskRequest, ChatMessageCreate, ConversationCreate
from app.core.config import get_settings
from app.integrations.runtime_cache import runtime_cache
from app.core.errors import AppError
from app.ai.tracing import persist_execution_trace
from app.ai.tutor import run_student_qa

router = APIRouter(prefix="/conversations", tags=["课程问答会话"])


def _owned_conversation(conversation_id: int, user: User, db: Session) -> Conversation:
    conversation = db.scalar(select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == user.id,
        Conversation.status == ConversationStatus.active,
    ))
    if conversation is None:
        raise NotFound("对话不存在")
    return conversation


def _view(row: Conversation) -> dict:
    return {
        "id": row.id,
        "offering_id": row.offering_id,
        "title": row.title,
        "summary": row.summary,
        "last_message_at": row.last_message_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("")
def list_conversations(
    request: Request,
    offering_id: int = Query(..., ge=1),
    user: User = Depends(require_roles(Role.student)),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(Conversation).where(
        Conversation.user_id == user.id,
        Conversation.offering_id == offering_id,
        Conversation.status == ConversationStatus.active,
    ).order_by(Conversation.last_message_at.desc(), Conversation.updated_at.desc())).all()
    return ok({"records": [_view(row) for row in rows]}, request.state.request_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate,
    request: Request,
    user: User = Depends(require_roles(Role.student)),
    db: Session = Depends(get_db),
):
    enrolled = db.scalar(select(Enrollment.id).where(
        Enrollment.offering_id == payload.offering_id,
        Enrollment.student_id == user.id,
    ))
    if not enrolled:
        raise Forbidden("只能在已加入的教学班中创建对话")
    conversation = Conversation(
        user_id=user.id,
        offering_id=payload.offering_id,
        title=payload.title.strip() or "新对话",
        status=ConversationStatus.active,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return ok(_view(conversation), request.state.request_id)


@router.get("/{conversation_id}/messages")
def list_messages(
    conversation_id: int,
    request: Request,
    user: User = Depends(require_roles(Role.student)),
    db: Session = Depends(get_db),
):
    _owned_conversation(conversation_id, user, db)
    rows = db.scalars(select(ChatMessage).where(
        ChatMessage.conversation_id == conversation_id,
    ).order_by(ChatMessage.sequence_no)).all()
    records = [{
        "id": row.id,
        "sequence_no": row.sequence_no,
        "role": row.role.value,
        "content": row.content,
        "status": row.status.value,
        "citations": row.citations,
        "policy_mode": row.policy_mode,
        "matched_assignment_id": row.matched_assignment_id,
        "similarity": (row.similarity / 100 if row.similarity is not None else None),
        "hint_level": row.hint_level,
        "created_at": row.created_at,
    } for row in rows]
    return ok({"records": records}, request.state.request_id)


@router.post("/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
def append_message(
    conversation_id: int,
    payload: ChatMessageCreate,
    request: Request,
    user: User = Depends(require_roles(Role.student)),
    db: Session = Depends(get_db),
):
    conversation = _owned_conversation(conversation_id, user, db)
    sequence_no = (db.scalar(select(func.max(ChatMessage.sequence_no)).where(
        ChatMessage.conversation_id == conversation_id,
    )) or 0) + 1
    message = ChatMessage(
        conversation_id=conversation_id,
        sequence_no=sequence_no,
        role=MessageRole(payload.role),
        content=payload.content,
        status=MessageStatus(payload.status),
    )
    now = datetime.now()
    conversation.last_message_at = now
    if payload.role == "user" and conversation.title == "新对话":
        normalized = " ".join(payload.content.split())
        conversation.title = normalized[:30] + ("…" if len(normalized) > 30 else "")
    db.add(message)
    db.commit()
    db.refresh(message)
    return ok({"id": message.id, "sequence_no": message.sequence_no,
               "title": conversation.title}, request.state.request_id)


def _similarity(left: str, right: str) -> float:
    left = re.sub(r"\s+", "", left.lower())
    right = re.sub(r"\s+", "", right.lower())
    if not left or not right:
        return 0.0
    sequence = SequenceMatcher(None, left, right).ratio()
    left_tokens = set(re.findall(r"[\w\u4e00-\u9fff]+", left))
    right_tokens = set(re.findall(r"[\w\u4e00-\u9fff]+", right))
    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens) if left_tokens | right_tokens else 0
    return max(sequence, jaccard)


@router.post("/{conversation_id}/ask", status_code=status.HTTP_201_CREATED)
def ask_tutor(conversation_id: int, payload: AskRequest, request: Request,
              user: User = Depends(require_roles(Role.student)), db: Session = Depends(get_db)):
    if not runtime_cache.allow("chat", user.id, 30, 60):
        raise AppError(429, "提问过于频繁，请稍后再试")
    conversation = _owned_conversation(conversation_id, user, db)
    run_kind = f"tutor:{hashlib.sha256(payload.idempotency_key.encode()).hexdigest()[:32]}"
    existing_run = db.scalar(select(AgentRun).where(
        AgentRun.kind == run_kind, AgentRun.owner_id == user.id
    ))
    if existing_run and existing_run.result:
        return ok(existing_run.result, request.state.request_id)
    open_questions = db.execute(
        select(Assignment.id, Question.prompt)
        .join(AssignmentQuestion, AssignmentQuestion.assignment_id == Assignment.id)
        .join(Question, Question.id == AssignmentQuestion.question_id)
        .where(
            Assignment.offering_id == conversation.offering_id,
            Assignment.status.in_([AssignmentStatus.open, AssignmentStatus.scheduled]),
            (Assignment.start_at.is_(None)) | (Assignment.start_at <= datetime.now()),
            (Assignment.end_at.is_(None)) | (Assignment.end_at > datetime.now()),
        )
    ).all()
    best_assignment = None
    best_similarity = 0.0
    for assignment_id, prompt in open_questions:
        value = _similarity(payload.content, prompt)
        if value > best_similarity:
            best_assignment, best_similarity = assignment_id, value
    guided = best_similarity >= 0.72
    started = datetime.now()
    recent_rows = list(reversed(db.scalars(select(ChatMessage).where(
        ChatMessage.conversation_id == conversation_id
    ).order_by(ChatMessage.sequence_no.desc()).limit(8)).all()))
    output = run_student_qa(
        db, student_id=user.id, offering_id=conversation.offering_id,
        question=payload.content, guided=guided,
        matched_assignment_id=best_assignment if guided else None,
        similarity=best_similarity,
        conversation_memory={
            "summary": conversation.summary,
            "recent_messages": [{"role": item.role.value, "content": item.content[:1500]}
                                for item in recent_rows],
        },
    )
    tutor_result = output["result"]
    citations = tutor_result.get("citations", [])
    answer = tutor_result["answer"]
    next_sequence = (db.scalar(select(func.max(ChatMessage.sequence_no)).where(
        ChatMessage.conversation_id == conversation_id)) or 0) + 1
    user_message = ChatMessage(
        conversation_id=conversation_id, sequence_no=next_sequence, role=MessageRole.user,
        content=payload.content, status=MessageStatus.completed,
        policy_mode="guided" if guided else "normal",
        matched_assignment_id=best_assignment if guided else None,
        similarity=round(best_similarity * 100) if guided else None, hint_level=payload.hint_level,
    )
    run = existing_run or AgentRun(
        kind=run_kind, agent_name="student_qa_agent", task_type=output["task_type"],
        owner_id=user.id,
        resource_type="conversation", resource_id=conversation_id,
        status=JobStatus.succeeded, graph_version="four-agent-v1",
        prompt_version="four-agent-prompts-v1", model=get_settings().llm_model,
    )
    db.add(user_message)
    db.add(run)
    db.flush()
    assistant_message = ChatMessage(
        conversation_id=conversation_id, sequence_no=next_sequence + 1, role=MessageRole.assistant,
        content=answer, status=MessageStatus.completed, citations=citations,
        policy_mode="guided" if guided else "normal",
        matched_assignment_id=best_assignment if guided else None,
        similarity=round(best_similarity * 100) if guided else None, hint_level=payload.hint_level,
    )
    result = {"user_message_id": user_message.id, "assistant_message_id": None,
              "answer": answer, "citations": citations, "policy_mode": assistant_message.policy_mode,
              "matched_assignment_id": assistant_message.matched_assignment_id,
              "similarity": best_similarity if guided else None, "agent_run_id": run.id}
    db.add(assistant_message)
    db.flush()
    result["assistant_message_id"] = assistant_message.id
    output["result"] = result
    persist_execution_trace(
        db, run, output,
        latency_ms=max(0, round((datetime.now() - started).total_seconds() * 1000)),
    )
    conversation.last_message_at = datetime.now()
    if conversation.title == "新对话":
        conversation.title = payload.content[:30] + ("…" if len(payload.content) > 30 else "")
    if next_sequence > 16:
        older = db.scalars(select(ChatMessage).where(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.role == MessageRole.user,
            ChatMessage.sequence_no <= next_sequence - 8,
        ).order_by(ChatMessage.sequence_no.desc()).limit(10)).all()
        conversation.summary = "此前对话主题：" + "；".join(
            " ".join(item.content.split())[:100] for item in reversed(older)
        )[:1800]
    db.commit()
    return ok(result, request.state.request_id)


@router.delete("/{conversation_id}")
def archive_conversation(
    conversation_id: int,
    request: Request,
    user: User = Depends(require_roles(Role.student)),
    db: Session = Depends(get_db),
):
    conversation = _owned_conversation(conversation_id, user, db)
    conversation.status = ConversationStatus.archived
    db.commit()
    return ok(None, request.state.request_id)
