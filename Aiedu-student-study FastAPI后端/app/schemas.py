from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models import AssignmentStatus, JobStatus, OfferingStatus, Role, SubmissionStatus


class LoginRequest(BaseModel):
    role: Role
    account: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenUser(BaseModel):
    id: int
    account: str
    name: str
    role: Role
    image: str | None = None
    token: str


class PasswordChange(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class PasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class AdminUserCreate(BaseModel):
    role: Role
    account: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class CourseCreate(BaseModel):
    number: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class OfferingCreate(BaseModel):
    course_id: int
    year: int = Field(ge=2000, le=2200)
    term: int = Field(ge=1, le=3)
    section_code: str = Field(default="01", min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    section_name: str | None = Field(default=None, max_length=100)


class EnrollmentCreate(BaseModel):
    student_account: str = Field(min_length=1, max_length=64)


class AssignmentCreate(BaseModel):
    offering_id: int
    title: str = Field(min_length=1, max_length=200)


class QuestionCreate(BaseModel):
    kind: Literal["short_answer", "single_choice", "multiple_choice", "programming"] = "short_answer"
    prompt: str = Field(min_length=1, max_length=100_000)
    reference_answer: str | None = Field(default=None, max_length=100_000)
    score: int = Field(gt=0, le=1000)
    difficulty: int = Field(default=0, ge=0, le=5)
    knowledge_point_ids: list[int] = Field(default_factory=list, max_length=20)


class AssignmentReplace(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    questions: list[QuestionCreate] = Field(default_factory=list, max_length=100)


class AssignmentPublish(BaseModel):
    start_at: datetime
    end_at: datetime
    idempotency_key: str = Field(min_length=8, max_length=128)


class AnswerInput(BaseModel):
    question_id: int
    content: str = Field(max_length=100_000)


class SubmissionSave(BaseModel):
    answers: list[AnswerInput]


class GradeItem(BaseModel):
    answer_id: int
    score: int = Field(ge=0)
    comment: str | None = Field(default=None, max_length=10_000)


class GradeRequest(BaseModel):
    items: list[GradeItem]
    overall_comment: str | None = Field(default=None, max_length=10_000)


class AIJobCreate(BaseModel):
    resource_id: int
    idempotency_key: str = Field(min_length=8, max_length=128)
    prompt: str | None = Field(default=None, max_length=20_000)


class ConversationCreate(BaseModel):
    offering_id: int
    title: str = Field(default="新对话", min_length=1, max_length=200)


class ChatMessageCreate(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=100_000)
    status: Literal["completed", "failed"] = "completed"


class AIJobView(BaseModel):
    id: int
    kind: str
    status: JobStatus
    progress: int
    result: dict | None = None
    error: str | None = None


class PromptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=1, max_length=50)
    content: str = Field(min_length=1, max_length=50_000)
    activate: bool = False


class KnowledgePointCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=200)
    parent_id: int | None = None
    description: str | None = Field(default=None, max_length=5000)


class QuestionKnowledgeBinding(BaseModel):
    knowledge_point_id: int
    weight: int = Field(default=100, ge=1, le=100)


class AssignmentDraftRequest(BaseModel):
    keywords: list[str] = Field(default_factory=list, max_length=20)
    knowledge_point_ids: list[int] = Field(default_factory=list, max_length=20)
    course_map_node_ids: list[int] = Field(default_factory=list, max_length=20)
    question_count: int = Field(default=5, ge=1, le=30)
    difficulty: int = Field(default=2, ge=1, le=5)
    question_kinds: list[Literal["short_answer", "single_choice", "multiple_choice", "programming"]] = Field(
        default_factory=lambda: ["short_answer"]
    )
    idempotency_key: str = Field(min_length=8, max_length=128)


class PracticeJobRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)
    knowledge_point_ids: list[int] = Field(default_factory=list, max_length=20)
    question_count: int = Field(default=5, ge=1, le=20)
    prompt: str | None = Field(default=None, max_length=5000)


class CourseMapDraftRequest(BaseModel):
    resource_ids: list[int] = Field(default_factory=list, max_length=50)
    prompt: str | None = Field(default=None, max_length=5000)
    idempotency_key: str = Field(min_length=8, max_length=128)


class AgentFeedbackCreate(BaseModel):
    feedback_type: Literal["accepted", "modified", "rejected"]
    before_value: dict | None = None
    after_value: dict | None = None
    comment: str | None = Field(default=None, max_length=5000)


class AskRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    idempotency_key: str = Field(min_length=8, max_length=128)
    hint_level: int = Field(default=0, ge=0, le=5)


class DirectThreadCreate(BaseModel):
    offering_id: int
    recipient_id: int


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20_000)


class CommunicationMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)


class ResourceMetadataUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
