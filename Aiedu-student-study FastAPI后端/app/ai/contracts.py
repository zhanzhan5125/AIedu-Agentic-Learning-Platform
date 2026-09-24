from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


AgentName = Literal[
    "teacher_course_assistant",
    "teacher_assessment_agent",
    "student_learning_assistant",
    "student_qa_agent",
]


class PlanStep(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    action: str = Field(min_length=1, max_length=100)
    tool: str | None = Field(default=None, max_length=100)
    reason: str = Field(min_length=1, max_length=500)


class AgentPlan(BaseModel):
    goal: str = Field(min_length=1, max_length=500)
    steps: list[PlanStep] = Field(min_length=1, max_length=4)
    max_tool_calls: int = Field(default=6, ge=1, le=6)
    max_reflections: int = Field(default=1, ge=0, le=1)


class Citation(BaseModel):
    chunk_id: int | None = None
    resource_id: int | None = None
    title: str
    position: int
    page_number: int | None = None
    slide_number: int | None = None
    heading_path: str | None = None
    excerpt: str = Field(default="", max_length=1200)
    score: float | None = None
    url: str | None = Field(default=None, max_length=2000)
    fetched_at: str | None = None
    source: Literal["course", "web"] = "course"


class CourseContextBrief(BaseModel):
    course_goal: str = "围绕当前课程资料与教学要求开展学习"
    current_scope: str = "当前已上传并完成索引的课程资料"
    key_points: list[str] = Field(default_factory=list, max_length=20)
    class_weak_points: list[str] = Field(default_factory=list, max_length=20)
    recommended_coverage: list[str] = Field(default_factory=list, max_length=20)
    citations: list[Citation] = Field(default_factory=list, max_length=12)


class StudentLearningPointBrief(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    chapter_name: str | None = Field(default=None, max_length=200)
    state: Literal["weak", "insufficient_data", "mastered"]
    mastery_score: int = Field(default=0, ge=0, le=100)
    recent_evidence: list[str] = Field(default_factory=list, max_length=5)


class StudentLearningBrief(BaseModel):
    summary: str
    student_name: str | None = Field(default=None, max_length=100)
    course_name: str | None = Field(default=None, max_length=200)
    weak_points: list[str] = Field(default_factory=list, max_length=20)
    insufficient_points: list[str] = Field(default_factory=list, max_length=20)
    mastered_points: list[str] = Field(default_factory=list, max_length=20)
    recommended_actions: list[str] = Field(default_factory=list, max_length=10)
    point_details: list[StudentLearningPointBrief] = Field(default_factory=list, max_length=20)


class AssignmentQuestionDraft(BaseModel):
    kind: Literal["short_answer", "single_choice", "multiple_choice", "programming"] = "short_answer"
    prompt: str = Field(min_length=1, max_length=20_000)
    reference_answer: str = Field(min_length=1, max_length=20_000)
    rubric: list[str] = Field(default_factory=list, max_length=10)
    score: int = Field(default=10, ge=1, le=1000)
    difficulty: int = Field(default=2, ge=1, le=5)
    knowledge_point_ids: list[int] = Field(default_factory=list, max_length=20)
    citations: list[Citation] = Field(default_factory=list, max_length=6)


class AssignmentDraftResult(BaseModel):
    rationale: str
    requires_teacher_review: bool = True
    questions: list[AssignmentQuestionDraft] = Field(min_length=1, max_length=30)


class GradeSuggestionItem(BaseModel):
    answer_id: int
    score: int = Field(ge=0)
    max_score: int = Field(ge=0)
    rubric: list[str] = Field(default_factory=list, max_length=8)
    comment: str
    error_type: str | None = None
    evidence_excerpt: str | None = None
    confidence: int = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def score_not_above_maximum(self):
        if self.score > self.max_score:
            raise ValueError("score cannot exceed max_score")
        return self


class GradingSuggestion(BaseModel):
    items: list[GradeSuggestionItem] = Field(default_factory=list)
    total_score: int = Field(default=0, ge=0)
    overall_comment: str
    confidence: int = Field(default=0, ge=0, le=100)
    needs_review: bool = True
    review_reason: str | None = None


class AssignmentQuestionSummary(BaseModel):
    question_id: int
    summary: str = Field(min_length=1, max_length=2000)
    strengths: list[str] = Field(default_factory=list, max_length=5)
    common_issues: list[str] = Field(default_factory=list, max_length=5)
    teaching_suggestion: str = Field(min_length=1, max_length=1000)
    confidence: int = Field(default=0, ge=0, le=100)


class AssignmentAnalysisResult(BaseModel):
    overall_summary: str = Field(min_length=1, max_length=5000)
    question_summaries: list[AssignmentQuestionSummary] = Field(default_factory=list, max_length=30)
    confidence: int = Field(default=0, ge=0, le=100)


class TutorAnswer(BaseModel):
    intent: Literal[
        "course_qa", "resource_lookup", "personalized_learning", "current_web",
        "assignment_guidance", "chitchat"
    ] = "course_qa"
    answer: str
    citations: list[Citation] = Field(default_factory=list, max_length=12)
    used_learning_profile: bool = False
    used_web_search: bool = False
    policy_mode: Literal["normal", "guided"] = "normal"
    evidence_sufficient: bool = True


class CourseMapNodeDraft(BaseModel):
    node_key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    position: int = Field(default=0, ge=0)
    confidence: int = Field(default=0, ge=0, le=100)
    evidence_chunk_ids: list[int] = Field(default_factory=list, max_length=20)

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, value):
        return max(0, min(100, int(value or 0)))


class CourseMapEdgeDraft(BaseModel):
    source_key: str
    target_key: str
    relation_type: Literal["contains", "next", "related"]
    confidence: int = Field(default=0, ge=0, le=100)
    evidence_chunk_ids: list[int] = Field(default_factory=list, max_length=20)

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, value):
        return max(0, min(100, int(value or 0)))


class CourseMapDraft(BaseModel):
    title: str = Field(default="课程知识路线", min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=5000)
    nodes: list[CourseMapNodeDraft] = Field(min_length=1, max_length=100)
    edges: list[CourseMapEdgeDraft] = Field(default_factory=list, max_length=300)

    @model_validator(mode="after")
    def validate_edges(self):
        keys = {node.node_key for node in self.nodes}
        if len(keys) != len(self.nodes):
            raise ValueError("course map node keys must be unique")
        for edge in self.edges:
            if edge.source_key not in keys or edge.target_key not in keys:
                raise ValueError("course map edge references an unknown node")
            if edge.source_key == edge.target_key:
                raise ValueError("course map edge cannot point to itself")
        return self


class CourseChapterPlanItem(BaseModel):
    chapter_key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1000)
    position: int = Field(default=0, ge=0)
    syllabus_chunk_ids: list[int] = Field(default_factory=list, max_length=8)


class CourseChapterPlan(BaseModel):
    title: str = Field(default="课程知识路线", min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=2000)
    chapters: list[CourseChapterPlanItem] = Field(min_length=1, max_length=20)


class ChapterKnowledgePointItem(BaseModel):
    chapter_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1000)
    evidence_chunk_ids: list[int] = Field(default_factory=list, max_length=8)


class ChapterKnowledgeBatch(BaseModel):
    knowledge_points: list[ChapterKnowledgePointItem] = Field(default_factory=list, max_length=12)


class ValidationResult(BaseModel):
    valid: bool
    issues: list[str] = Field(default_factory=list, max_length=20)
    evidence_sufficient: bool = True
    requires_human_review: bool = False


class AgentExecutionResult(BaseModel):
    agent_name: AgentName
    task_type: str
    plan: AgentPlan
    result: dict[str, Any]
    validation: ValidationResult
    reflection_count: int = Field(default=0, ge=0, le=1)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    delegations: list[dict[str, Any]] = Field(default_factory=list)
    token_usage: dict[str, int | None] | None = None
