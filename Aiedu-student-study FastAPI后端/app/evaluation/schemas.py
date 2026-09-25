from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictEvalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RelevantChunk(StrictEvalModel):
    resource_title: str = Field(min_length=1, max_length=255)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    relevance: int = Field(ge=1, le=3)


class RAGEvalCase(StrictEvalModel):
    id: str = Field(pattern=r"^rag-[0-9]{3}$")
    category: Literal["exact", "semantic", "chapter", "multi_evidence", "unanswerable"]
    query: str = Field(min_length=2, max_length=500)
    answerable: bool = True
    relevant_chunks: list[RelevantChunk] = Field(default_factory=list)
    end_to_end: bool = False
    approved: bool = False

    @model_validator(mode="after")
    def relevance_matches_answerability(self):
        if self.answerable and not self.relevant_chunks:
            raise ValueError("可回答问题必须标注至少一个相关切片")
        if not self.answerable and self.relevant_chunks:
            raise ValueError("不可回答问题不能标注相关切片")
        return self


class RAGEvalDataset(StrictEvalModel):
    version: str
    offering_id: int = Field(gt=0)
    contains_personal_data: Literal[False] = False
    cases: list[RAGEvalCase]


class GradingAnswerCase(StrictEvalModel):
    id: str
    kind: Literal["short_answer", "single_choice", "multiple_choice", "programming"]
    prompt: str = Field(min_length=1, max_length=20_000)
    reference_answer: str = Field(min_length=1, max_length=20_000)
    rubric: list[str] = Field(min_length=1, max_length=8)
    max_score: int = Field(gt=0, le=1000)
    student_answer: str = Field(max_length=20_000)
    gold_score: int = Field(ge=0)
    accepted_min: int = Field(ge=0)
    accepted_max: int = Field(ge=0)
    should_review: bool = False

    @model_validator(mode="after")
    def validate_gold_range(self):
        if not 0 <= self.accepted_min <= self.gold_score <= self.accepted_max <= self.max_score:
            raise ValueError("人工评分区间必须包含 gold_score 且不能超过满分")
        return self


class GradingSubmissionCase(StrictEvalModel):
    id: str = Field(pattern=r"^grading-[0-9]{3}$")
    source: Literal["synthetic", "deidentified"]
    teacher_rules: str = "按参考答案和评分要点公平评分"
    answers: list[GradingAnswerCase] = Field(min_length=1)
    approved: bool = False


class GradingEvalDataset(StrictEvalModel):
    version: str
    contains_personal_data: Literal[False] = False
    submissions: list[GradingSubmissionCase]


class RoutingExpectation(StrictEvalModel):
    intent: Literal["course_qa", "resource_lookup", "personalized_learning", "current_web", "chitchat"]
    delegate_student_learning_assistant: bool
    search_course_materials: bool
    search_web: bool
    identity_request: bool


class RoutingEvalCase(StrictEvalModel):
    id: str = Field(pattern=r"^routing-[0-9]{3}$")
    category: str = Field(min_length=1, max_length=50)
    question: str = Field(min_length=1, max_length=1000)
    conversation_summary: str | None = Field(default=None, max_length=3000)
    recent_messages: list[dict[str, str]] = Field(default_factory=list, max_length=4)
    expected: RoutingExpectation
    repeat: bool = False
    approved: bool = False


class RoutingEvalDataset(StrictEvalModel):
    version: str
    contains_personal_data: Literal[False] = False
    cases: list[RoutingEvalCase]


def assert_official_dataset(dataset: BaseModel, suite: str) -> None:
    values = dataset.cases if hasattr(dataset, "cases") else dataset.submissions
    unapproved = [item.id for item in values if not item.approved]
    if unapproved:
        raise ValueError(f"{suite} 评测集包含未人工确认样本：{', '.join(unapproved[:10])}")
    expected = {"rag": 40, "grading": 10, "routing": 40}[suite]
    if len(values) != expected:
        raise ValueError(f"{suite} 正式评测集应有 {expected} 组，当前为 {len(values)}")
    if suite == "grading":
        answer_count = sum(len(item.answers) for item in values)
        if answer_count != 30:
            raise ValueError(f"grading 正式评测集应有 30 条答案，当前为 {answer_count}")
    if suite == "rag":
        answerable = sum(item.answerable for item in values)
        e2e = sum(item.end_to_end for item in values)
        if answerable != 32 or e2e != 12:
            raise ValueError("RAG 正式评测集必须包含 32 条可回答问题和 12 条端到端样本")
    ids = [item.id for item in values]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{suite} 评测集存在重复 ID")
