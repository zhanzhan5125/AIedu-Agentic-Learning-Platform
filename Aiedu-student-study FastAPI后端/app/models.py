from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Role(str, enum.Enum):
    manager = "manager"
    teacher = "teacher"
    student = "student"


class OfferingStatus(str, enum.Enum):
    planned = "planned"
    active = "active"
    ended = "ended"
    archived = "archived"


class AssignmentStatus(str, enum.Enum):
    draft = "draft"
    scheduled = "scheduled"
    open = "open"
    closed = "closed"
    grading = "grading"
    graded = "graded"


class SubmissionStatus(str, enum.Enum):
    not_started = "not_started"
    draft = "draft"
    submitted = "submitted"
    ai_grading = "ai_grading"
    needs_review = "needs_review"
    graded = "graded"
    returned = "returned"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class ConversationStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class MessageRole(str, enum.Enum):
    system = "system"
    user = "user"
    assistant = "assistant"
    tool = "tool"


class MessageStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ProcessingStatus(str, enum.Enum):
    uploaded = "uploaded"
    scanning = "scanning"
    parsing = "parsing"
    indexing = "indexing"
    ready = "ready"
    failed = "failed"
    deleted = "deleted"


class CommunicationKind(str, enum.Enum):
    announcement = "announcement"
    direct = "direct"
    system = "system"
    agent_status = "agent_status"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "app_users"
    __table_args__ = (UniqueConstraint("role", "account", name="uq_user_role_account"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[Role] = mapped_column(Enum(Role), index=True)
    account: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    password_migrated: Mapped[bool] = mapped_column(Boolean, default=True)


class Course(TimestampMixin, Base):
    __tablename__ = "app_courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class CourseOffering(TimestampMixin, Base):
    __tablename__ = "course_offerings"
    __table_args__ = (
        UniqueConstraint("course_id", "year", "term", "section_code", name="uq_offering_course_term_section"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("app_courses.id", ondelete="RESTRICT"))
    teacher_id: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="RESTRICT"))
    year: Mapped[int]
    term: Mapped[int]
    section_code: Mapped[str] = mapped_column(String(32), default="01")
    section_name: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[OfferingStatus] = mapped_column(Enum(OfferingStatus), default=OfferingStatus.planned)
    course: Mapped[Course] = relationship()
    teacher: Mapped[User] = relationship()


class Enrollment(TimestampMixin, Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("offering_id", "student_id", name="uq_enrollment"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    offering_id: Mapped[int] = mapped_column(ForeignKey("course_offerings.id", ondelete="CASCADE"))
    student_id: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"))


class Assignment(TimestampMixin, Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    offering_id: Mapped[int] = mapped_column(ForeignKey("course_offerings.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[AssignmentStatus] = mapped_column(Enum(AssignmentStatus), default=AssignmentStatus.draft)
    start_at: Mapped[datetime | None]
    end_at: Mapped[datetime | None]
    total_score: Mapped[int] = mapped_column(default=0)
    origin: Mapped[str] = mapped_column(String(32), default="manual")
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"))


class Question(TimestampMixin, Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), default="short_answer")
    prompt: Mapped[str] = mapped_column(Text)
    reference_answer: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int] = mapped_column(default=0)
    difficulty: Mapped[int] = mapped_column(default=0)


class AssignmentQuestion(Base):
    __tablename__ = "assignment_questions"
    __table_args__ = (
        UniqueConstraint("assignment_id", "position", name="uq_assignment_position"),
        UniqueConstraint("assignment_id", "question_id", name="uq_assignment_question"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"))
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"))
    position: Mapped[int]


class Submission(TimestampMixin, Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("assignment_id", "student_id", name="uq_submission"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"))
    student_id: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="RESTRICT"))
    status: Mapped[SubmissionStatus] = mapped_column(Enum(SubmissionStatus), default=SubmissionStatus.not_started)
    submitted_at: Mapped[datetime | None]
    ai_graded_at: Mapped[datetime | None]
    graded_at: Mapped[datetime | None]
    grading_source: Mapped[str | None] = mapped_column(String(32))
    review_reason: Mapped[str | None] = mapped_column(String(500))
    ai_confidence: Mapped[int | None]
    total_score: Mapped[int] = mapped_column(default=0)
    teacher_comment: Mapped[str | None] = mapped_column(Text)
    ai_comment: Mapped[str | None] = mapped_column(Text)


class Answer(TimestampMixin, Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("submission_id", "question_id", name="uq_answer"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"))
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"))
    content: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int] = mapped_column(default=0)
    teacher_comment: Mapped[str | None] = mapped_column(Text)
    ai_comment: Mapped[str | None] = mapped_column(Text)
    ai_raw: Mapped[dict | None] = mapped_column(JSON)


class PromptTemplate(TimestampMixin, Base):
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    purpose: Mapped[str] = mapped_column(String(50), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class PromptVersion(TimestampMixin, Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("template_id", "version", name="uq_prompt_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("prompt_templates.id", ondelete="CASCADE"))
    version: Mapped[int]
    content: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[int] = mapped_column(ForeignKey("app_users.id"))


class AIJob(TimestampMixin, Base):
    __tablename__ = "ai_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"))
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[int]
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.queued, index=True)
    progress: Mapped[int] = mapped_column(default=0)
    input_data: Mapped[dict] = mapped_column(JSON)
    result_data: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"))


class Conversation(TimestampMixin, Base):
    """Durable course-scoped chat session; vector data does not belong here."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_user_status_updated", "user_id", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"))
    offering_id: Mapped[int] = mapped_column(ForeignKey("course_offerings.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200), default="新对话")
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus), default=ConversationStatus.active
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime)


class ChatMessage(TimestampMixin, Base):
    """Canonical chat history stored in MySQL, including AI job traceability."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence_no", name="uq_chat_message_sequence"),
        Index("ix_chat_messages_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    sequence_no: Mapped[int]
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole))
    content: Mapped[str | None] = mapped_column(Text)
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus), default=MessageStatus.pending
    )
    ai_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_jobs.id", ondelete="SET NULL")
    )
    citations: Mapped[list | dict | None] = mapped_column(JSON)
    token_count: Mapped[int | None]
    knowledge_point_ids: Mapped[list | None] = mapped_column(JSON)
    policy_mode: Mapped[str | None] = mapped_column(String(32))
    matched_assignment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assignments.id", ondelete="SET NULL")
    )
    similarity: Mapped[int | None]
    hint_level: Mapped[int | None]


class OutboxEvent(TimestampMixin, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_pending", "published_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(100))
    tag: Mapped[str] = mapped_column(String(100))
    aggregate_id: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON)
    published_at: Mapped[datetime | None]
    attempts: Mapped[int] = mapped_column(default=0)


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    offering_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_offerings.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)


class FileObject(TimestampMixin, Base):
    __tablename__ = "file_objects"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int]


class KnowledgePoint(TimestampMixin, Base):
    __tablename__ = "knowledge_points"
    __table_args__ = (UniqueConstraint("course_id", "code", name="uq_knowledge_course_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("app_courses.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_points.id", ondelete="SET NULL"))
    description: Mapped[str | None] = mapped_column(Text)


class QuestionKnowledgePoint(Base):
    __tablename__ = "question_knowledge_points"
    __table_args__ = (UniqueConstraint("question_id", "knowledge_point_id", name="uq_question_knowledge"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    knowledge_point_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True)
    weight: Mapped[int] = mapped_column(default=100)


class AgentRun(TimestampMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_resource", "resource_type", "resource_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    agent_name: Mapped[str | None] = mapped_column(String(64), index=True)
    task_type: Mapped[str | None] = mapped_column(String(64), index=True)
    parent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), index=True
    )
    owner_id: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="RESTRICT"))
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[int]
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.queued, index=True)
    graph_version: Mapped[str] = mapped_column(String(32), default="v1")
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(100))
    latency_ms: Mapped[int | None]
    token_usage: Mapped[dict | None] = mapped_column(JSON)
    plan: Mapped[dict | None] = mapped_column(JSON)
    reflection_count: Mapped[int] = mapped_column(default=0)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)


class AgentRunStep(TimestampMixin, Base):
    __tablename__ = "agent_run_steps"
    __table_args__ = (UniqueConstraint("run_id", "position", name="uq_agent_run_step_position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int]
    node_name: Mapped[str] = mapped_column(String(100))
    agent_name: Mapped[str | None] = mapped_column(String(64))
    step_type: Mapped[str | None] = mapped_column(String(32))
    tool_name: Mapped[str | None] = mapped_column(String(100))
    input_digest: Mapped[str | None] = mapped_column(String(128))
    output_summary: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    duration_ms: Mapped[int | None]


class LearningEvidence(TimestampMixin, Base):
    __tablename__ = "learning_evidence"
    __table_args__ = (
        UniqueConstraint("student_id", "knowledge_point_id", "source_type", "source_id", name="uq_learning_evidence_source"),
        Index("ix_learning_evidence_profile", "student_id", "offering_id", "knowledge_point_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"))
    offering_id: Mapped[int] = mapped_column(ForeignKey("course_offerings.id", ondelete="CASCADE"))
    knowledge_point_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[int]
    score: Mapped[int]
    weight: Mapped[int]
    confidence: Mapped[int]
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"))


class StudentMasteryProfile(TimestampMixin, Base):
    __tablename__ = "student_mastery_profiles"
    __table_args__ = (UniqueConstraint("student_id", "offering_id", "knowledge_point_id", name="uq_student_mastery"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"))
    offering_id: Mapped[int] = mapped_column(ForeignKey("course_offerings.id", ondelete="CASCADE"))
    knowledge_point_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id", ondelete="CASCADE"))
    mastery_score: Mapped[int]
    confidence: Mapped[int]
    observation_count: Mapped[int]
    trend: Mapped[str] = mapped_column(String(16), default="stable")
    last_observed_at: Mapped[datetime]
    version: Mapped[int] = mapped_column(default=1)


class ClassMasterySnapshot(TimestampMixin, Base):
    __tablename__ = "class_mastery_snapshots"
    __table_args__ = (Index("ix_class_mastery_latest", "offering_id", "snapshot_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    offering_id: Mapped[int] = mapped_column(ForeignKey("course_offerings.id", ondelete="CASCADE"))
    knowledge_point_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id", ondelete="CASCADE"))
    weak_student_count: Mapped[int]
    student_count: Mapped[int]
    average_mastery: Mapped[int]
    snapshot_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AnswerAnalysis(TimestampMixin, Base):
    __tablename__ = "answer_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    answer_id: Mapped[int] = mapped_column(ForeignKey("answers.id", ondelete="CASCADE"), unique=True)
    error_type: Mapped[str | None] = mapped_column(String(100))
    misconception: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[int]
    evidence: Mapped[dict | None] = mapped_column(JSON)
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"))


class CourseResource(TimestampMixin, Base):
    __tablename__ = "course_resources"
    __table_args__ = (
        UniqueConstraint("offering_id", "sha256", "version", name="uq_resource_version"),
        Index("ix_resource_offering_status", "offering_id", "processing_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    offering_id: Mapped[int] = mapped_column(ForeignKey("course_offerings.id", ondelete="CASCADE"))
    uploader_id: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(255))
    resource_type: Mapped[str] = mapped_column(String(32), default="courseware")
    original_name: Mapped[str] = mapped_column(String(255))
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(default=1)
    visibility: Mapped[str] = mapped_column(String(32), default="course")
    processing_status: Mapped[ProcessingStatus] = mapped_column(Enum(ProcessingStatus), default=ProcessingStatus.uploaded)
    error_message: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None]
    chunk_count: Mapped[int | None]
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    indexed_at: Mapped[datetime | None]
    deleted_at: Mapped[datetime | None]


class ResourceChunk(TimestampMixin, Base):
    __tablename__ = "resource_chunks"
    __table_args__ = (
        UniqueConstraint("resource_id", "position", name="uq_resource_chunk_position"),
        Index("ix_resource_chunks_offering_resource", "offering_id", "resource_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("course_resources.id", ondelete="CASCADE"), index=True
    )
    offering_id: Mapped[int] = mapped_column(
        ForeignKey("course_offerings.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]
    block_type: Mapped[str] = mapped_column(String(32), default="paragraph")
    heading_path: Mapped[str | None] = mapped_column(String(500))
    page_number: Mapped[int | None]
    slide_number: Mapped[int | None]
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int]
    content_hash: Mapped[str] = mapped_column(String(64), index=True)


class CourseMapVersion(TimestampMixin, Base):
    __tablename__ = "course_map_versions"
    __table_args__ = (
        UniqueConstraint("course_id", "version", name="uq_course_map_version"),
        Index("ix_course_map_course_status", "course_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("app_courses.id", ondelete="CASCADE"), index=True
    )
    offering_id: Mapped[int] = mapped_column(
        ForeignKey("course_offerings.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int]
    status: Mapped[str] = mapped_column(String(24), default="draft")
    title: Mapped[str] = mapped_column(String(200), default="课程知识路线")
    summary: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="RESTRICT"))
    agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    published_at: Mapped[datetime | None]


class CourseMapNode(TimestampMixin, Base):
    __tablename__ = "course_map_nodes"
    __table_args__ = (
        UniqueConstraint("version_id", "node_key", name="uq_course_map_node_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("course_map_versions.id", ondelete="CASCADE"), index=True
    )
    node_key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(default=0)
    confidence: Mapped[int] = mapped_column(default=0)
    knowledge_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="SET NULL")
    )


class CourseMapEdge(TimestampMixin, Base):
    __tablename__ = "course_map_edges"
    __table_args__ = (
        UniqueConstraint("version_id", "source_node_id", "target_node_id", "relation_type",
                         name="uq_course_map_edge"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("course_map_versions.id", ondelete="CASCADE"), index=True
    )
    source_node_id: Mapped[int] = mapped_column(
        ForeignKey("course_map_nodes.id", ondelete="CASCADE")
    )
    target_node_id: Mapped[int] = mapped_column(
        ForeignKey("course_map_nodes.id", ondelete="CASCADE")
    )
    relation_type: Mapped[str] = mapped_column(String(24))
    confidence: Mapped[int] = mapped_column(default=0)


class CourseMapEvidence(TimestampMixin, Base):
    __tablename__ = "course_map_evidence"
    __table_args__ = (
        Index("ix_course_map_evidence_target", "node_id", "edge_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_map_nodes.id", ondelete="CASCADE")
    )
    edge_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_map_edges.id", ondelete="CASCADE")
    )
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("resource_chunks.id", ondelete="CASCADE"), index=True
    )


class AgentFeedback(TimestampMixin, Base):
    __tablename__ = "agent_feedback"
    __table_args__ = (Index("ix_agent_feedback_run", "run_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="RESTRICT"))
    feedback_type: Mapped[str] = mapped_column(String(24))
    before_value: Mapped[dict | None] = mapped_column(JSON)
    after_value: Mapped[dict | None] = mapped_column(JSON)
    comment: Mapped[str | None] = mapped_column(Text)


class CommunicationThread(TimestampMixin, Base):
    __tablename__ = "communication_threads"

    id: Mapped[int] = mapped_column(primary_key=True)
    offering_id: Mapped[int] = mapped_column(ForeignKey("course_offerings.id", ondelete="CASCADE"), index=True)
    kind: Mapped[CommunicationKind] = mapped_column(Enum(CommunicationKind))
    title: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="RESTRICT"))
    last_message_at: Mapped[datetime | None]


class CommunicationMember(TimestampMixin, Base):
    __tablename__ = "communication_members"
    __table_args__ = (UniqueConstraint("thread_id", "user_id", name="uq_communication_member"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("communication_threads.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    last_read_message_id: Mapped[int | None]


class CommunicationMessage(TimestampMixin, Base):
    __tablename__ = "communication_messages"
    __table_args__ = (Index("ix_communication_message_thread", "thread_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("communication_threads.id", ondelete="CASCADE"))
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("app_users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text)
    message_type: Mapped[str] = mapped_column(String(32), default="text")


class ScheduledNotification(TimestampMixin, Base):
    __tablename__ = "scheduled_notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    offering_id: Mapped[int] = mapped_column(ForeignKey("course_offerings.id", ondelete="CASCADE"))
    assignment_id: Mapped[int | None] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(50))
    scheduled_at: Mapped[datetime]
    dedup_key: Mapped[str] = mapped_column(String(160), unique=True)
    sent_at: Mapped[datetime | None]
    payload: Mapped[dict] = mapped_column(JSON)


class ConsumerInbox(TimestampMixin, Base):
    __tablename__ = "consumer_inbox"
    __table_args__ = (UniqueConstraint("event_id", "consumer_name", name="uq_consumer_event"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int]
    consumer_name: Mapped[str] = mapped_column(String(100))
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class PracticeSession(TimestampMixin, Base):
    __tablename__ = "practice_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"))
    offering_id: Mapped[int] = mapped_column(ForeignKey("course_offerings.id", ondelete="CASCADE"))
    assignment_id: Mapped[int | None] = mapped_column(ForeignKey("assignments.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(32), default="ready")
    rationale: Mapped[str | None] = mapped_column(Text)
    questions: Mapped[list] = mapped_column(JSON)
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"))


class AssignmentInsightSnapshot(TimestampMixin, Base):
    __tablename__ = "assignment_insight_snapshots"
    __table_args__ = (UniqueConstraint("assignment_id", "version", name="uq_assignment_insight_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    version: Mapped[int]
    data: Mapped[dict] = mapped_column(JSON)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
