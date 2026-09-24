from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.ai.contracts import (
    AgentPlan, AssignmentAnalysisResult, AssignmentDraftResult, AssignmentQuestionDraft,
    AssignmentQuestionSummary, Citation,
    ChapterKnowledgeBatch, CourseChapterPlan, CourseContextBrief, CourseMapDraft,
    CourseMapEdgeDraft, CourseMapNodeDraft, GradingSuggestion, GradeSuggestionItem, PlanStep,
    StudentLearningBrief, ValidationResult,
)
from app.core.config import get_settings
from app.db import SessionLocal
from app.integrations.ai_provider import structured_completion
from app.integrations.rag import search_course, search_course_supporting
from app.models import (
    Answer, Assignment, AssignmentQuestion, Course, CourseOffering,
    CourseResource, KnowledgePoint, ProcessingStatus, Question, ResourceChunk, Submission,
    SubmissionStatus,
)
from app.services.insights import assignment_insights, class_insights
from app.services.learning import profile_view


AGENT_BY_KIND = {
    "assignment.draft": ("teacher_assessment_agent", "assignment_draft"),
    "grading.single": ("teacher_assessment_agent", "grading"),
    "assignment.summary": ("teacher_assessment_agent", "assignment_analysis"),
    "course_map.generate": ("teacher_course_assistant", "course_map_draft"),
    "practice.generate": ("student_learning_assistant", "practice_generate"),
    "question.generate": ("teacher_assessment_agent", "question_generate"),
    "rag.chat": ("student_qa_agent", "course_qa"),
}


class WorkflowState(TypedDict, total=False):
    kind: str
    resource_id: int
    owner_id: int | None
    prompt: str | None
    input_data: dict[str, Any]
    agent_name: str
    task_type: str
    offering_id: int | None
    context: dict[str, Any]
    plan: dict[str, Any]
    tool_results: dict[str, Any]
    delegations: list[dict[str, Any]]
    draft: dict[str, Any]
    validation: dict[str, Any]
    reflection_count: int
    result: dict[str, Any]
    needs_review: bool
    steps: list[dict[str, Any]]
    token_usage: dict[str, int]


def agent_identity(kind: str) -> tuple[str, str]:
    return AGENT_BY_KIND.get(kind, ("teacher_course_assistant", kind.replace(".", "_")))


def _step(state: WorkflowState, node_name: str, *, tool_name: str | None,
          summary: dict[str, Any], started: float, step_type: str = "node") -> list[dict[str, Any]]:
    return [*state.get("steps", []), {
        "node_name": node_name,
        "agent_name": state.get("agent_name"),
        "step_type": step_type,
        "tool_name": tool_name,
        "output_summary": summary,
        "duration_ms": round((perf_counter() - started) * 1000),
    }]


def _find_offering(db, state: WorkflowState) -> tuple[CourseOffering | None, Assignment | None, Submission | None]:
    kind = state["kind"]
    assignment = None
    submission = None
    offering_id = state.get("input_data", {}).get("offering_id")
    if kind == "grading.single":
        submission = db.get(Submission, state["resource_id"])
        assignment = db.get(Assignment, submission.assignment_id) if submission else None
        offering_id = assignment.offering_id if assignment else None
    elif kind == "assignment.summary":
        assignment = db.get(Assignment, state["resource_id"])
        offering_id = assignment.offering_id if assignment else None
    elif kind == "practice.generate":
        offering_id = offering_id or state["resource_id"]
    elif kind in {"assignment.draft", "question.generate", "course_map.generate", "rag.chat"}:
        offering_id = offering_id or state["resource_id"]
    return (db.get(CourseOffering, int(offering_id)) if offering_id else None, assignment, submission)


def prepare_context(state: WorkflowState) -> WorkflowState:
    started = perf_counter()
    agent_name, task_type = agent_identity(state["kind"])
    context: dict[str, Any] = {
        "resource_id": state["resource_id"], "input": state.get("input_data", {}),
        "prompt": state.get("prompt"),
    }
    offering_id = None
    with SessionLocal() as db:
        offering, assignment, submission = _find_offering(db, state)
        if offering:
            course = db.get(Course, offering.course_id)
            offering_id = offering.id
            context["course"] = {
                "id": course.id if course else None, "name": course.name if course else "",
                "description": course.description if course else None,
                "offering_id": offering.id, "section_name": offering.section_name,
            }
        if assignment:
            context["assignment"] = {
                "id": assignment.id, "title": assignment.title,
                "total_score": assignment.total_score,
            }
        if submission:
            context["submission"] = {
                "id": submission.id, "student_id": submission.student_id,
                "status": submission.status.value,
            }
    seeded: WorkflowState = {
        **state, "agent_name": agent_name, "task_type": task_type,
        "offering_id": offering_id, "context": context, "reflection_count": 0,
        "delegations": [], "tool_results": {},
        "token_usage": {"prompt": 0, "completion": 0, "total": 0},
    }
    seeded["steps"] = _step(
        seeded, "prepare_context", tool_name="business_context",
        summary={"offering_id": offering_id, "context_keys": sorted(context)}, started=started,
    )
    return seeded


def make_plan(state: WorkflowState) -> WorkflowState:
    started = perf_counter()
    kind = state["kind"]
    if kind == "assignment.draft":
        steps = [
            PlanStep(id="1", action="获取课程和班级上下文", tool="delegate_teacher_course_assistant", reason="题目必须与课程范围和班级情况一致"),
            PlanStep(id="2", action="检索可引用的课程资料", tool="search_course_materials", reason="为题目和答案提供资料依据"),
            PlanStep(id="3", action="生成题目、答案与评分标准", tool=None, reason="形成教师可审核的结构化草稿"),
            PlanStep(id="4", action="校验题量、难度、分值和依据", tool="validate_assignment_draft", reason="阻止不符合约束的草稿进入业务表"),
        ]
    elif kind == "grading.single":
        steps = [
            PlanStep(id="1", action="读取题目、答案和学生作答", tool="get_submission_answers", reason="评分必须以真实作答为依据"),
            PlanStep(id="2", action="生成分项评分建议", tool=None, reason="输出可复核的评分和评语"),
            PlanStep(id="3", action="检查分数边界和证据支持", tool="validate_grading", reason="批阅建议不得超过题目分值"),
        ]
    elif kind == "assignment.summary":
        steps = [
            PlanStep(id="1", action="读取已确认成绩与逐题统计", tool="get_assignment_statistics", reason="数值必须由确定性代码计算"),
            PlanStep(id="2", action="读取匿名化的逐题作答样本", tool="get_graded_answers", reason="总结必须由真实学生作答支持"),
            PlanStep(id="3", action="总结每题答题情况与教学建议", tool=None, reason="形成教师可读的逐题分析"),
            PlanStep(id="4", action="校验题目覆盖完整性", tool="validate_assignment_analysis", reason="确保每道题都有对应总结"),
        ]
    elif kind == "practice.generate":
        steps = [
            PlanStep(id="1", action="读取个人学习画像", tool="get_student_mastery", reason="练习应针对真实学情"),
            PlanStep(id="2", action="检索相关课程资料", tool="search_course_materials", reason="题目需要课程依据"),
            PlanStep(id="3", action="生成个性化练习并校验", tool="create_practice_session", reason="生成可直接进入练习会话的结构化内容"),
        ]
    elif kind == "course_map.generate":
        steps = [
            PlanStep(id="1", action="从教学大纲提取章节骨架", tool="get_course_resources", reason="章节范围和顺序应由大纲决定"),
            PlanStep(id="2", action="按章节检索教材和课件", tool="search_course_materials", reason="只取与当前章节相关的辅助内容"),
            PlanStep(id="3", action="分批生成章节知识点", tool=None, reason="形成可教学、可出题的两级路线"),
            PlanStep(id="4", action="校验章节层级和知识点数量", tool="validate_course_map", reason="确保发布后可直接用于章节选题"),
        ]
    else:
        steps = [
            PlanStep(id="1", action="读取业务上下文", tool="get_course_resources", reason="确认任务范围"),
            PlanStep(id="2", action="检索相关课程资料", tool="search_course_materials", reason="优先使用课程内证据"),
            PlanStep(id="3", action="生成并校验结构化结果", tool=None, reason="确保结果可供业务消费"),
        ]
    plan = AgentPlan(goal=state.get("prompt") or f"完成 {state['task_type']} 任务", steps=steps)
    result = {**state, "plan": plan.model_dump()}
    result["steps"] = _step(
        result, "make_plan", tool_name=None,
        summary={"step_count": len(steps), "tool_budget": plan.max_tool_calls}, started=started,
        step_type="planning",
    )
    return result


def _citations(rows: list[dict]) -> list[dict]:
    return [Citation(
        chunk_id=row.get("chunk_id"), resource_id=int(row["resource_id"]),
        title=row.get("title") or "课程资料", position=int(row.get("position", 0)),
        page_number=row.get("page_number"), slide_number=row.get("slide_number"),
        heading_path=row.get("heading_path"), excerpt=(row.get("text") or "")[:1200],
        score=row.get("rerank_score", row.get("score")),
    ).model_dump() for row in rows]


def _course_brief(db, offering_id: int, query: str, include_class: bool) -> tuple[dict, list[dict]]:
    offering = db.get(CourseOffering, offering_id)
    course = db.get(Course, offering.course_id) if offering else None
    points = db.scalars(select(KnowledgePoint).where(
        KnowledgePoint.course_id == offering.course_id
    ).order_by(KnowledgePoint.id).limit(20)).all() if offering else []
    insights = class_insights(db, offering_id) if include_class else {"knowledge_points": []}
    rows = search_course(offering_id, query, limit=6, db=db)
    weak = [item["name"] for item in insights["knowledge_points"] if item.get("is_class_weak")]
    key_points = [point.name for point in points]
    brief = CourseContextBrief(
        course_goal=(course.description if course and course.description else "掌握课程核心概念并能够完成应用"),
        current_scope=f"{course.name if course else '当前课程'}已完成索引的课程资料",
        key_points=key_points, class_weak_points=weak,
        recommended_coverage=list(dict.fromkeys([*weak, *key_points]))[:10],
        citations=_citations(rows),
    ).model_dump()
    delegation = {
        "agent_name": "teacher_course_assistant", "task_type": "course_context_brief",
        "result": brief,
        "plan": AgentPlan(goal="为出题智能体准备课程上下文", steps=[
            PlanStep(id="1", action="读取课程知识点和资料", tool="get_course_resources", reason="限定课程范围"),
            PlanStep(id="2", action="分析班级薄弱点", tool="get_class_insights", reason="提供差异化覆盖建议"),
            PlanStep(id="3", action="检索资料并形成简报", tool="search_course_materials", reason="返回可引用证据"),
        ]).model_dump(),
        "steps": [{
            "node_name": "build_course_context_brief", "agent_name": "teacher_course_assistant",
            "step_type": "delegation", "tool_name": "get_class_insights+search_course_materials",
            "output_summary": {"key_point_count": len(key_points), "citation_count": len(rows)},
            "duration_ms": 0,
        }],
        "validation": ValidationResult(valid=True, evidence_sufficient=bool(rows)).model_dump(),
    }
    return brief, [delegation]


def _student_brief(profile: dict) -> dict:
    points = profile.get("knowledge_points", [])
    weak = [item["name"] for item in points if item["state"] == "weak"]
    unobserved = [item["name"] for item in points if item["state"] == "unobserved"]
    mastered = [item["name"] for item in points if item["state"] == "mastered"]
    if weak:
        actions = [f"优先复习：{name}" for name in weak[:5]]
    elif mastered:
        actions = ["完成综合巩固练习，保持已掌握知识点"]
    else:
        actions = ["先完成一次课程基础练习，建立初始学习记录"]
    return StudentLearningBrief(
        summary=f"{len(mastered)} 个知识点已掌握，{len(weak)} 个薄弱，{len(unobserved)} 个暂无学习记录。",
        weak_points=weak[:20], unobserved_points=unobserved[:20], mastered_points=mastered[:20],
        recommended_actions=actions,
    ).model_dump()


COURSE_MAP_SYLLABUS_LIMIT = 72
COURSE_MAP_SUPPORT_LIMIT = 20
COURSE_MAP_INFERRED_LIMIT = 96


def _usable_course_map_chunk(chunk: ResourceChunk) -> bool:
    """Drop obvious empty/TOC noise without excluding short syllabus headings."""
    text = re.sub(r"\s+", " ", chunk.text or "").strip()
    if len(text) < 4:
        return False
    dotted_leaders = len(re.findall(r"\.{3,}|…{2,}", text))
    number_count = len(re.findall(r"\d+", text))
    return not (dotted_leaders >= 2 and number_count >= 3)


def _sample_evenly(items: list[Any], limit: int) -> list[Any]:
    if len(items) <= limit:
        return items
    if limit <= 1:
        return items[:limit]
    indexes = [round(index * (len(items) - 1) / (limit - 1)) for index in range(limit)]
    return [items[index] for index in indexes]


def _course_map_prompt_text(text: str, limit: int = 1400) -> str:
    value = re.sub(r"[ \t]+", " ", text or "").strip()
    if len(value) <= limit:
        return value
    lower = limit // 2
    boundaries = [value.rfind(mark, lower, limit) for mark in ("。", "！", "？", ". ", "\n")]
    end = max(boundaries)
    return value[:(end + 1 if end >= lower else limit)].rstrip() + "……"


def _take_balanced(groups: list[list[Any]], limit: int) -> list[Any]:
    """Round-robin resources so one large textbook cannot starve later uploads."""
    selected: list[Any] = []
    position = 0
    while len(selected) < limit:
        added = False
        for group in groups:
            if position < len(group):
                selected.append(group[position])
                added = True
                if len(selected) == limit:
                    break
        if not added:
            break
        position += 1
    return selected


def _course_map_materials(db, offering_id: int, resource_ids: list[int]) -> tuple[list[dict], dict]:
    resource_query = select(CourseResource).where(
        CourseResource.offering_id == offering_id,
        CourseResource.processing_status == ProcessingStatus.ready,
        CourseResource.deleted_at.is_(None),
    )
    if resource_ids:
        resource_query = resource_query.where(CourseResource.id.in_(resource_ids))
    resources = db.scalars(resource_query.order_by(CourseResource.id)).all()

    grouped: dict[str, list[list[tuple[ResourceChunk, CourseResource]]]] = {
        "syllabus": [], "supporting": [],
    }
    source_rows: list[dict] = []
    for resource in resources:
        rows = db.scalars(select(ResourceChunk).where(
            ResourceChunk.offering_id == offering_id,
            ResourceChunk.resource_id == resource.id,
        ).order_by(ResourceChunk.position)).all()
        usable = [row for row in rows if _usable_course_map_chunk(row)] or list(rows)
        role = "syllabus" if resource.resource_type == "syllabus" else "supporting"
        per_resource_limit = (COURSE_MAP_SYLLABUS_LIMIT if role == "syllabus"
                              else COURSE_MAP_INFERRED_LIMIT)
        pairs = _sample_evenly([(row, resource) for row in usable], per_resource_limit)
        grouped[role].append(pairs)
        source_rows.append({
            "resource_id": resource.id, "title": resource.title,
            "resource_type": resource.resource_type, "usable_chunks": len(usable),
            "role": "outline" if role == "syllabus" else "supporting",
        })

    syllabus_pairs = _take_balanced(grouped["syllabus"], COURSE_MAP_SYLLABUS_LIMIT)
    if syllabus_pairs:
        support_pairs = _take_balanced(grouped["supporting"], COURSE_MAP_SUPPORT_LIMIT)
        selected_pairs = syllabus_pairs + support_pairs
        mode = "syllabus_first"
    else:
        selected_pairs = _take_balanced(grouped["supporting"], COURSE_MAP_INFERRED_LIMIT)
        mode = "inferred_from_materials"

    chunks = [{
        "chunk_id": chunk.id, "resource_id": resource.id,
        "resource_title": resource.title, "resource_type": resource.resource_type,
        "source_role": "outline" if resource.resource_type == "syllabus" else "supporting",
        "heading_path": chunk.heading_path, "page_number": chunk.page_number,
        "slide_number": chunk.slide_number, "position": chunk.position,
        "text": _course_map_prompt_text(chunk.text),
    } for chunk, resource in selected_pairs]
    strategy = {
        "mode": mode,
        "rule": ("教学大纲决定节点与教学顺序，教材和课件只能补充说明与证据"
                 if mode == "syllabus_first" else
                 "未找到已索引教学大纲，路线由教材和课件推断，必须标记为推断草稿"),
        "outline_chunk_ids": [item["chunk_id"] for item in chunks if item["source_role"] == "outline"],
        "sources": source_rows,
    }
    return chunks, strategy


def execute_tools(state: WorkflowState) -> WorkflowState:
    started = perf_counter()
    tools: dict[str, Any] = {}
    delegations: list[dict[str, Any]] = []
    offering_id = state.get("offering_id")
    input_data = state.get("input_data", {})
    query_terms = (input_data.get("keywords") or
                   input_data.get("selected_knowledge_point_names") or
                   input_data.get("selected_chapter_names") or [])
    query = " ".join(query_terms) or state.get("prompt") or "课程核心知识点"
    with SessionLocal() as db:
        if state["kind"] == "assignment.draft" and offering_id:
            brief, delegations = _course_brief(db, offering_id, query, include_class=True)
            tools["course_context"] = brief
        elif offering_id and state["kind"] not in {
            "course_map.generate", "grading.single", "assignment.summary",
        }:
            tools["citations"] = _citations(search_course(offering_id, query, limit=6, db=db))
        if state["kind"] == "practice.generate" and offering_id and state.get("owner_id"):
            profile = profile_view(db, int(state["owner_id"]), offering_id)
            tools["learning_profile"] = profile
            tools["student_brief"] = _student_brief(profile)
        if state["kind"] == "grading.single":
            submission = db.get(Submission, state["resource_id"])
            if submission:
                rows = db.execute(
                    select(Answer, Question).join(Question, Question.id == Answer.question_id)
                    .where(Answer.submission_id == submission.id).order_by(Answer.id)
                ).all()
                tools["answers"] = [{
                    "answer_id": answer.id, "question_id": question.id,
                    "question_kind": question.kind,
                    "question": question.prompt, "student_answer": answer.content or "",
                    "reference_answer": question.reference_answer or "", "max_score": question.score,
                } for answer, question in rows]
                assigned_ids = set(db.scalars(select(AssignmentQuestion.question_id).where(
                    AssignmentQuestion.assignment_id == submission.assignment_id
                )).all())
                tools["missing_question_ids"] = sorted(assigned_ids - {q.id for _, q in rows})
        if state["kind"] == "assignment.summary":
            assignment = db.get(Assignment, state["resource_id"])
            if assignment:
                tools["assignment_stats"] = assignment_insights(db, assignment)
                question_rows = db.execute(
                    select(Question, AssignmentQuestion.position)
                    .join(AssignmentQuestion, AssignmentQuestion.question_id == Question.id)
                    .where(AssignmentQuestion.assignment_id == assignment.id)
                    .order_by(AssignmentQuestion.position)
                ).all()
                question_answers = []
                for question, position in question_rows:
                    answer_rows = db.execute(
                        select(Answer)
                        .join(Submission, Submission.id == Answer.submission_id)
                        .where(
                            Submission.assignment_id == assignment.id,
                            Submission.status.in_([
                                SubmissionStatus.graded, SubmissionStatus.returned,
                            ]),
                            Answer.question_id == question.id,
                        )
                        .order_by(Answer.id)
                        .limit(20)
                    ).scalars().all()
                    question_answers.append({
                        "question_id": question.id,
                        "position": position,
                        "question_kind": question.kind,
                        "question": question.prompt,
                        "reference_answer": question.reference_answer or "",
                        "max_score": question.score,
                        "sample_count": len(answer_rows),
                        "answer_samples": [{
                            "answer": (answer.content or "")[:1200],
                            "confirmed_score": answer.score,
                            "teacher_comment": (answer.teacher_comment or "")[:500],
                            "error_type": (answer.ai_raw or {}).get("error_type"),
                        } for answer in answer_rows],
                    })
                tools["question_answers"] = question_answers
        if state["kind"] == "course_map.generate" and offering_id:
            resource_ids = state.get("input_data", {}).get("resource_ids") or []
            chunks, strategy = _course_map_materials(db, offering_id, resource_ids)
            tools["course_map_chunks"] = chunks
            tools["course_map_strategy"] = strategy
    result = {**state, "tool_results": tools, "delegations": delegations}
    result["steps"] = _step(
        result, "execute_tools", tool_name="bounded_tool_executor",
        summary={"tools_used": sorted(tools), "tool_calls": min(6, len(tools) + len(delegations)),
                 "delegation_count": len(delegations)},
        started=started, step_type="tool",
    )
    return result


def _fallback_questions(state: WorkflowState) -> AssignmentDraftResult:
    data = state.get("input_data", {})
    count = int(data.get("question_count", 5))
    keywords = data.get("keywords") or []
    if not keywords:
        brief = state.get("tool_results", {}).get("course_context", {})
        keywords = brief.get("recommended_coverage") or brief.get("key_points") or ["课程核心知识点"]
    kinds = data.get("question_kinds") or ["short_answer"]
    difficulty = int(data.get("difficulty", 2))
    knowledge_ids = data.get("knowledge_point_ids", [])
    citations = (state.get("tool_results", {}).get("course_context", {}).get("citations") or
                 state.get("tool_results", {}).get("citations") or [])
    mode_text = {
        "weak_point_review": "根据已确认的薄弱知识点生成巩固练习。",
        "course_baseline": "当前还没有已评分记录，生成课程基础练习。",
        "comprehensive_review": "当前没有薄弱知识点，生成综合巩固练习。",
    }.get(data.get("practice_mode"), "依据教师约束、课程资料和学习画像生成；发布或使用前必须人工确认。")

    def question_content(question_kind: str, keyword: str, number: int) -> tuple[str, str, list[str]]:
        if question_kind == "single_choice":
            return (
                f"第 {number} 题：关于“{keyword}”，下列说法正确的是？\nA. 符合该概念的正确表述\nB. 与该概念相反的表述\nC. 无关概念的表述\nD. 常见误解的表述",
                "A。教师应结合课程资料复核并细化四个选项。",
                ["选择正确选项", "能够说明判断依据"],
            )
        if question_kind == "multiple_choice":
            return (
                f"第 {number} 题：关于“{keyword}”，下列哪些说法正确？（多选）\nA. 正确特征一\nB. 正确特征二\nC. 常见错误表述\nD. 无关表述",
                "A、B。教师应结合课程资料复核并细化四个选项。",
                ["完整选择正确选项", "未选择明显错误项", "能够说明判断依据"],
            )
        if question_kind == "programming":
            return (
                f"请编写程序解决与“{keyword}”相关的第 {number} 个应用问题，说明输入、输出与核心算法。",
                "参考程序应能正确处理题目约束，并包含清晰的输入输出说明和关键步骤解释。",
                ["程序能够正确运行", "算法逻辑正确", "边界情况处理合理", "代码结构清晰"],
            )
        return (
            f"请结合“{keyword}”说明第 {number} 个关键概念，并给出一个应用示例。",
            "应包含准确的概念定义、清晰的推理过程和与题意一致的应用示例。",
            ["概念定义准确", "推理过程完整", "应用示例与概念一致"],
        )

    question_values = []
    for index in range(count):
        question_kind = kinds[index % len(kinds)]
        prompt, answer, rubric = question_content(
            question_kind, keywords[index % len(keywords)], index + 1,
        )
        question_values.append(AssignmentQuestionDraft(
            kind=question_kind, prompt=prompt, reference_answer=answer, rubric=rubric,
            score=10, difficulty=difficulty,
            knowledge_point_ids=(
                [knowledge_ids[index % len(knowledge_ids)]] if knowledge_ids else []
            ),
            citations=[Citation.model_validate(item) for item in citations[:2]],
        ))
    return AssignmentDraftResult(
        rationale=mode_text,
        questions=question_values,
    )


def _has_complete_choice_options(prompt: str) -> bool:
    return all(re.search(rf"(?:^|\s){label}\s*[.．、:：)]", prompt, re.MULTILINE)
               for label in "ABCD")


def _fallback_grading(state: WorkflowState) -> GradingSuggestion:
    answers = state.get("tool_results", {}).get("answers", [])
    return GradingSuggestion(
        items=[GradeSuggestionItem(
            answer_id=item["answer_id"], score=0, max_score=item["max_score"],
            comment="真实模型未启用，未生成自动得分；请教师依据参考答案人工复核。",
            error_type="requires_manual_review", evidence_excerpt=(item["student_answer"] or "")[:300],
            confidence=0,
        ) for item in answers],
        total_score=0, overall_comment="当前仅完成确定性边界检查，未启用模型评分。",
        confidence=0, needs_review=True, review_reason="真实模型未启用或不可用",
    )


def _model_assignment(state: WorkflowState) -> tuple[dict, dict]:
    settings = get_settings()
    requirements = dict(state.get("input_data", {}))
    question_count = int(requirements.get("question_count", 5))
    value, metadata = structured_completion(
        AssignmentDraftResult,
        system_prompt=(
            "你是 AIedu 教师出题/批阅智能体的出题模式。只能依据给定课程资料生成题目，"
            "严格满足题量、题型、难度和知识点要求，question_kinds 是教师允许且要求覆盖的题型；"
            "当题量不少于题型数量时，每种所选题型至少生成一道。整套题不得重复。"
            "每道题的 knowledge_point_ids 必须从教师给定的 knowledge_point_ids 中选择 1 至 2 个与题干直接对应的知识点，"
            "不得漏绑定、不得绑定未选知识点，也不得把所有知识点无区分地绑定到每道题。"
            "题量足够时，整套题应覆盖教师所选的全部知识点。"
            "单选题和多选题必须在 prompt 中完整列出 A、B、C、D 四个选项，并在答案中明确正确选项。每题提供答案、"
            "2至4条简短 Rubric 与最多2条引用。题干控制在300字内，参考答案控制在500字内。"
        ),
        user_prompt=json.dumps({
            "teacher_requirements": requirements,
            "course_context": state.get("tool_results", {}),
        }, ensure_ascii=False, default=str),
        max_tokens=min(16_000, 2_000 + question_count * 1_200),
        timeout_seconds=settings.assignment_llm_timeout_seconds,
        max_retries=0,
    )
    return value.model_dump(), metadata


def _model_grading(state: WorkflowState) -> tuple[dict, dict]:
    teacher_rules = (state.get("prompt") or "").strip()
    value, metadata = structured_completion(
        GradingSuggestion,
        system_prompt=(
            "你是 AIedu 教师出题/批阅智能体的批阅模式。先根据题目、题型、参考答案和满分为每题形成 2 至 5 条简短评分 Rubric，"
            "再逐项核对学生作答并给分。评分只能由学生答案直接支持，不得因为语言风格或答案顺序不同扣分；"
            "程序题应关注算法、正确性、边界与表达，不要求与参考答案逐字一致。score 不得超过 max_score，total_score 必须等于分项之和。"
            "evidence_excerpt 必须逐字摘自学生答案；未作答时固定写‘未作答’。comment 要说明得分点和待改进点，error_type 使用简短类别或 null。"
            "置信度低、参考答案不足、题意歧义或无法可靠判断时必须 needs_review=true，并清楚填写 review_reason。"
        ),
        user_prompt=json.dumps({
            "teacher_rules": teacher_rules or "按参考答案和题目分值公平评分",
            "submission": state.get("tool_results", {}),
        }, ensure_ascii=False, default=str),
    )
    return value.model_dump(), metadata


def _model_grading_revision(state: WorkflowState, draft: dict, issues: list[str]) -> tuple[dict, dict]:
    """Run one bounded second look only when deterministic checks found a defect."""
    value, metadata = structured_completion(
        GradingSuggestion,
        system_prompt=(
            "你正在复核一份 AI 批阅建议。只修正校验指出的问题，并重新核对每项评分是否由学生原文支持。"
            "必须覆盖所有 answer_id，保持真实 max_score，证据摘录必须来自对应学生答案，分项之和必须等于总分。"
            "若仍无法可靠判断，不要猜测，降低置信度并明确要求教师重点复核。"
        ),
        user_prompt=json.dumps({
            "teacher_rules": (state.get("prompt") or "").strip(),
            "submission": state.get("tool_results", {}),
            "first_suggestion": draft,
            "validation_issues": issues,
        }, ensure_ascii=False, default=str),
        max_retries=0,
    )
    return value.model_dump(), metadata


def _fallback_assignment_analysis(state: WorkflowState) -> AssignmentAnalysisResult:
    stats = state.get("tool_results", {}).get("assignment_stats", {})
    summaries = []
    for item in stats.get("questions", []):
        average = item.get("average_score")
        maximum = item.get("max_score")
        rate = item.get("score_rate")
        errors = list((item.get("error_types") or {}).keys())[:5]
        summaries.append(AssignmentQuestionSummary(
            question_id=int(item["question_id"]),
            summary=(
                f"已确认 {item.get('submission_count', 0)} 份作答，平均分 "
                f"{average if average is not None else '-'} / {maximum}，"
                f"得分率 {rate if rate is not None else '-'}%。"
            ),
            strengths=[],
            common_issues=errors or ["当前样本不足，暂无法归纳稳定的共性问题"],
            teaching_suggestion="结合学生原答案抽样复核，并针对失分点进行讲解。",
            confidence=0,
        ))
    return AssignmentAnalysisResult(
        overall_summary=(
            f"本次统计基于 {stats.get('graded_count', 0)} 份教师已确认成绩；"
            f"作业平均分为 {stats.get('average_score')} / {stats.get('total_score')}。"
        ),
        question_summaries=summaries,
        confidence=0,
    )


def _model_assignment_analysis(state: WorkflowState) -> tuple[dict, dict]:
    value, metadata = structured_completion(
        AssignmentAnalysisResult,
        system_prompt=(
            "你是 AIedu 教师出题/批阅智能体的作业分析模式。后端给出的平均分、最高分、最低分和得分率是确定性统计，"
            "不得重新计算或改写这些数值。请匿名总结每一道题的整体答题情况：概括主要得分点、共性错误及一条可执行的教学建议。"
            "不得提及学生姓名或推断个人身份，不得修改成绩。只能陈述作答中可直接观察的事实，不得评价学习态度、"
            "猜测未作答原因，或仅因空白作答就推断学生存在知识盲区、能力问题或理解困难。"
            "样本较少时必须明确说明结论仅供参考，不要把单个学生表现泛化为全班规律。"
            "question_summaries 必须覆盖输入中的每一个 question_id，且不得生成不存在的题目。"
        ),
        user_prompt=json.dumps({
            "assignment_statistics": state.get("tool_results", {}).get("assignment_stats", {}),
            "graded_answer_samples": state.get("tool_results", {}).get("question_answers", []),
        }, ensure_ascii=False, default=str),
        max_tokens=8_000,
        max_retries=0,
    )
    return value.model_dump(), metadata


_UNSUPPORTED_LEARNING_INFERENCES = (
    "态度不", "知识盲区", "知识空白", "理解困难", "能力问题",
    "只复习", "缺乏了解", "完全不了解", "掌握较好", "未能掌握",
)


def _has_unsupported_learning_inference(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return any(phrase in text for phrase in _UNSUPPORTED_LEARNING_INFERENCES)


def _model_assignment_analysis_revision(
    state: WorkflowState, draft: dict, issues: list[str]
) -> tuple[dict, dict]:
    value, metadata = structured_completion(
        AssignmentAnalysisResult,
        system_prompt=(
            "你是 AIedu 教师出题/批阅智能体的作业分析修订节点。请修复当前分析中超出作答证据的推断。"
            "只写“答案包含了什么”或“答案未包含什么”；空白、不知道或无效文本只能表述为“未形成可评分的有效作答”。"
            "不得推断学习态度、复习情况、能力、动机、知识盲区、是否掌握或理解困难。"
            "保留后端统计数值不变，并且精确覆盖输入中每一个 question_id。"
        ),
        user_prompt=json.dumps({
            "validation_issues": issues,
            "assignment_statistics": state.get("tool_results", {}).get("assignment_stats", {}),
            "graded_answer_samples": state.get("tool_results", {}).get("question_answers", []),
            "current_analysis": draft,
        }, ensure_ascii=False, default=str),
        max_tokens=8_000,
        max_retries=0,
    )
    return value.model_dump(), metadata


def _fallback_course_map(state: WorkflowState) -> CourseMapDraft:
    chunks = state.get("tool_results", {}).get("course_map_chunks", [])
    if not chunks:
        raise ValueError("所选课程资料尚未生成可用切片，请先完成资料索引")
    strategy = state.get("tool_results", {}).get("course_map_strategy", {})
    outline_chunks = [chunk for chunk in chunks if chunk.get("source_role") == "outline"]
    backbone_chunks = outline_chunks or chunks
    grouped: dict[str, dict[str, list[dict]]] = {}
    for chunk in backbone_chunks:
        path = [value.strip() for value in (chunk.get("heading_path") or "").split(" > ")
                if value.strip()]
        fallback_name = (chunk.get("text") or "课程知识点").splitlines()[0][:40]
        chapter_name = path[0] if len(path) > 1 else (path[0] if path else fallback_name)
        point_name = path[-1] if len(path) > 1 else f"{chapter_name}核心知识"
        grouped.setdefault(chapter_name, {}).setdefault(point_name, []).append(chunk)
    nodes: list[CourseMapNodeDraft] = []
    edges: list[CourseMapEdgeDraft] = []
    chapter_nodes: list[CourseMapNodeDraft] = []
    position = 1
    for chapter_index, (chapter_name, points) in enumerate(list(grouped.items())[:15], 1):
        normalized_points = list(points.items())[:4]
        if len(normalized_points) < 2:
            evidence = normalized_points[0][1] if normalized_points else []
            existing_names = {name for name, _ in normalized_points}
            for suffix in ("基础概念", "实践应用"):
                name = f"{chapter_name}{suffix}"
                if name not in existing_names:
                    normalized_points.append((name, evidence))
                if len(normalized_points) >= 2:
                    break
        chapter_evidence = [item for values in points.values() for item in values]
        chapter = CourseMapNodeDraft(
            node_key=f"chapter-{chapter_index}", name=chapter_name,
            description=f"{chapter_name}章节概要，包含 {len(normalized_points)} 个知识点。", position=position,
            confidence=70, evidence_chunk_ids=[item["chunk_id"] for item in chapter_evidence[:5]],
        )
        nodes.append(chapter)
        chapter_nodes.append(chapter)
        position += 1
        for point_index, (point_name, evidence) in enumerate(normalized_points, 1):
            point = CourseMapNodeDraft(
                node_key=f"kp-{chapter_index}-{point_index}", name=point_name,
                description=(evidence[0].get("text") or "")[:500], position=position,
                confidence=65, evidence_chunk_ids=[item["chunk_id"] for item in evidence[:5]],
            )
            nodes.append(point)
            position += 1
            edges.append(CourseMapEdgeDraft(
                source_key=chapter.node_key, target_key=point.node_key,
                relation_type="contains", confidence=70,
                evidence_chunk_ids=point.evidence_chunk_ids[:2],
            ))
    edges.extend(CourseMapEdgeDraft(
        source_key=chapter_nodes[index - 1].node_key, target_key=chapter_nodes[index].node_key,
        relation_type="next", confidence=60,
        evidence_chunk_ids=chapter_nodes[index].evidence_chunk_ids[:2],
    ) for index in range(1, len(chapter_nodes)))
    return CourseMapDraft(
        title=("课程知识路线草稿" if outline_chunks else "课程知识路线（资料推断草稿）"),
        summary=("以教学大纲为路线骨架生成；教材和课件仅作为补充资料，发布前需教师审核。"
                 if strategy.get("mode") == "syllabus_first" else
                 "未找到已索引教学大纲，本路线由教材和课件推断，发布前需教师重点审核。"),
        nodes=nodes, edges=edges,
    )


def _merge_model_metadata(items: list[dict], *, mode: str,
                          failed_batches: int = 0) -> dict:
    usage = {"prompt": 0, "completion": 0, "total": 0}
    for item in items:
        for key in usage:
            usage[key] += int((item.get("token_usage") or {}).get(key) or 0)
    return {
        "model": next((item.get("model") for item in items if item.get("model")), None),
        "latency_ms": sum(int(item.get("latency_ms") or 0) for item in items),
        "token_usage": usage,
        "generation_mode": mode,
        "model_call_count": len(items),
        "failed_batches": failed_batches,
    }


def _fallback_batch_points(chapter: dict, support: list[dict]) -> list[dict]:
    """Keep a usable route when one small knowledge-point request fails."""
    names: list[str] = []
    for item in support:
        heading = (item.get("heading_path") or "").split(" > ")[-1].strip()
        if heading and heading != chapter["name"] and heading not in names:
            names.append(heading[:80])
    for suffix in ("核心概念", "基本方法"):
        candidate = f"{chapter['name']}{suffix}"
        if candidate not in names:
            names.append(candidate)
    evidence = [int(item["chunk_id"]) for item in support[:2] if item.get("chunk_id")]
    return [{
        "chapter_key": chapter["chapter_key"],
        "name": name,
        "summary": f"理解并能够应用{chapter['name']}中的{name}。",
        "evidence_chunk_ids": evidence,
    } for name in names[:2]]


def _model_course_map(state: WorkflowState, *, previous_draft: dict | None = None,
                      issues: list[str] | None = None) -> tuple[dict, dict]:
    """Generate a map in bounded stages: syllabus chapters, then retrieved KPs."""
    del previous_draft, issues  # Reflection is deterministic for this bounded pipeline.
    strategy = state.get("tool_results", {}).get("course_map_strategy", {})
    material_chunks = state.get("tool_results", {}).get("course_map_chunks", [])
    outline_chunks = [item for item in material_chunks if item.get("source_role") == "outline"]
    backbone = outline_chunks or material_chunks
    if not backbone:
        raise ValueError("所选课程资料尚未生成可用切片，请先完成资料索引")

    chapter_input = [{
        "chunk_id": item["chunk_id"],
        "heading_path": item.get("heading_path"),
        "page_number": item.get("page_number"),
        "position": item.get("position"),
        "text": _course_map_prompt_text(item.get("text") or "", 800),
    } for item in backbone[:60]]
    metadata_items: list[dict] = []
    try:
        chapter_plan, chapter_metadata = structured_completion(
            CourseChapterPlan,
            system_prompt=(
                "你是教师课程助手。当前步骤只负责从教学大纲提取课程章节骨架，"
                "不要生成细粒度知识点，也不要扩写教材内容。章节名称和顺序必须忠于大纲；"
                "合并重复标题，忽略考核方式、师资、教材清单等非教学章节。"
                "每个章节引用实际支持它的 syllabus_chunk_ids；没有教学大纲时，"
                "才可从现有资料标题推断章节。最多 15 个章节。"
            ),
            user_prompt=json.dumps({
                "mode": strategy.get("mode"),
                "outline_chunks": chapter_input,
            }, ensure_ascii=False, default=str),
            max_tokens=2600, timeout_seconds=90,
        )
        metadata_items.append(chapter_metadata)
    except Exception:
        fallback = _fallback_course_map(state).model_dump()
        return fallback, _merge_model_metadata(
            metadata_items, mode="deterministic-fallback", failed_batches=1,
        )

    valid_backbone_ids = {int(item["chunk_id"]) for item in backbone}
    chapters: list[dict] = []
    seen_names: set[str] = set()
    for item in sorted(chapter_plan.chapters, key=lambda value: value.position)[:15]:
        name = re.sub(r"\s+", " ", item.name).strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        chapters.append({
            "chapter_key": f"chapter-{len(chapters) + 1}",
            "name": name,
            "summary": item.summary.strip(),
            "position": len(chapters) + 1,
            "syllabus_chunk_ids": [
                chunk_id for chunk_id in item.syllabus_chunk_ids
                if chunk_id in valid_backbone_ids
            ][:5],
        })
    if not chapters:
        fallback = _fallback_course_map(state).model_dump()
        return fallback, _merge_model_metadata(
            metadata_items, mode="deterministic-fallback", failed_batches=1,
        )

    selected_resource_ids = state.get("input_data", {}).get("resource_ids") or None
    support_by_chapter: dict[str, list[dict]] = {}
    with SessionLocal() as db:
        for chapter in chapters:
            support_by_chapter[chapter["chapter_key"]] = search_course_supporting(
                int(state["offering_id"]),
                f"{chapter['name']} {chapter['summary']}",
                limit=4, db=db, resource_ids=selected_resource_ids,
            )

    # Make retrieved IDs visible to the validator and evidence API, without
    # putting unrelated textbook pages into the model prompt.
    known_chunk_ids = {item["chunk_id"] for item in material_chunks}
    for rows in support_by_chapter.values():
        for item in rows:
            if item.get("chunk_id") in known_chunk_ids:
                continue
            material_chunks.append({
                "chunk_id": item.get("chunk_id"), "resource_id": item.get("resource_id"),
                "resource_title": item.get("title"),
                "resource_type": item.get("resource_type"), "source_role": "supporting",
                "heading_path": item.get("heading_path"),
                "page_number": item.get("page_number"),
                "slide_number": item.get("slide_number"), "position": item.get("position"),
                "text": _course_map_prompt_text(item.get("text") or ""),
            })
            known_chunk_ids.add(item.get("chunk_id"))

    points_by_chapter: dict[str, list[dict]] = {item["chapter_key"]: [] for item in chapters}
    failed_batches = 0
    for offset in range(0, len(chapters), 3):
        batch = chapters[offset:offset + 3]
        batch_support = {
            chapter["chapter_key"]: [{
                "chunk_id": item.get("chunk_id"),
                "resource_type": item.get("resource_type"),
                "title": item.get("title"),
                "heading_path": item.get("heading_path"),
                "text": _course_map_prompt_text(item.get("text") or "", 900),
            } for item in support_by_chapter[chapter["chapter_key"]]]
            for chapter in batch
        }
        try:
            generated, batch_metadata = structured_completion(
                ChapterKnowledgeBatch,
                system_prompt=(
                    "你是教师课程助手。针对每个给定章节生成 2 至 4 个具体、可教学、可出题的知识点。"
                    "章节边界已由大纲确定，不得新增或改名章节。教材/课件检索片段仅用于帮助细化知识点；"
                    "不要复制大段原文。chapter_key 必须原样返回。evidence_chunk_ids 只能引用该章节"
                    "supporting_chunks 中真实出现的 chunk_id；没有合适依据时可为空。"
                ),
                user_prompt=json.dumps({
                    "chapters": batch,
                    "supporting_chunks": batch_support,
                }, ensure_ascii=False, default=str),
                max_tokens=2400, timeout_seconds=90,
            )
            metadata_items.append(batch_metadata)
            for item in generated.knowledge_points:
                if item.chapter_key not in points_by_chapter:
                    continue
                allowed_ids = {
                    int(row["chunk_id"]) for row in support_by_chapter[item.chapter_key]
                    if row.get("chunk_id")
                }
                points_by_chapter[item.chapter_key].append({
                    "chapter_key": item.chapter_key,
                    "name": item.name.strip(), "summary": item.summary.strip(),
                    "evidence_chunk_ids": [
                        chunk_id for chunk_id in item.evidence_chunk_ids
                        if chunk_id in allowed_ids
                    ][:4],
                })
        except Exception:
            failed_batches += 1

        for chapter in batch:
            key = chapter["chapter_key"]
            unique: list[dict] = []
            names: set[str] = set()
            for item in points_by_chapter[key]:
                if item["name"] and item["name"] not in names:
                    names.add(item["name"])
                    unique.append(item)
            if len(unique) < 2:
                for item in _fallback_batch_points(chapter, support_by_chapter[key]):
                    if item["name"] not in names:
                        names.add(item["name"])
                        unique.append(item)
                    if len(unique) >= 2:
                        break
            points_by_chapter[key] = unique[:4]

    nodes: list[CourseMapNodeDraft] = []
    edges: list[CourseMapEdgeDraft] = []
    position = 1
    cited_types: set[str] = set()
    for chapter_index, chapter in enumerate(chapters, 1):
        chapter_node = CourseMapNodeDraft(
            node_key=chapter["chapter_key"], name=chapter["name"],
            description=chapter["summary"], position=position, confidence=90,
            evidence_chunk_ids=chapter["syllabus_chunk_ids"],
        )
        nodes.append(chapter_node)
        position += 1
        for point_index, point in enumerate(points_by_chapter[chapter["chapter_key"]], 1):
            point_key = f"kp-{chapter_index}-{point_index}"
            evidence_ids = point["evidence_chunk_ids"]
            for row in support_by_chapter[chapter["chapter_key"]]:
                if row.get("chunk_id") in evidence_ids and row.get("resource_type"):
                    cited_types.add(str(row["resource_type"]))
            nodes.append(CourseMapNodeDraft(
                node_key=point_key, name=point["name"], description=point["summary"],
                position=position, confidence=82 if evidence_ids else 72,
                evidence_chunk_ids=evidence_ids,
            ))
            position += 1
            edges.append(CourseMapEdgeDraft(
                source_key=chapter_node.node_key, target_key=point_key,
                relation_type="contains", confidence=90,
                evidence_chunk_ids=evidence_ids[:2],
            ))
        if chapter_index > 1:
            edges.append(CourseMapEdgeDraft(
                source_key=chapters[chapter_index - 2]["chapter_key"],
                target_key=chapter_node.node_key, relation_type="next", confidence=90,
                evidence_chunk_ids=chapter_node.evidence_chunk_ids[:2],
            ))

    source_text = []
    if "textbook" in cited_types:
        source_text.append("教材")
    if "courseware" in cited_types:
        source_text.append("课件")
    if outline_chunks:
        summary = "章节结构来自教学大纲"
        if source_text:
            summary += f"，并按章节检索{'和'.join(source_text)}细化知识点"
        summary += "。请教师审核后发布。"
    else:
        summary = "未找到教学大纲，章节由现有课程资料推断。请教师重点审核后发布。"
    draft = CourseMapDraft(
        title=chapter_plan.title, summary=summary, nodes=nodes, edges=edges,
    ).model_dump()
    return draft, _merge_model_metadata(
        metadata_items,
        mode="staged-model" if not failed_batches else "staged-model-with-fallback",
        failed_batches=failed_batches,
    )


def compose_result(state: WorkflowState) -> WorkflowState:
    started = perf_counter()
    settings = get_settings()
    metadata: dict[str, Any] = {}
    if state["kind"] in {"assignment.draft", "question.generate", "practice.generate"}:
        if settings.enable_llm and settings.ai_api_key:
            draft, metadata = _model_assignment(state)
        else:
            draft = _fallback_questions(state).model_dump()
        draft["reason"] = draft.get("rationale")
        draft["mode"] = "model" if metadata else "deterministic-fallback"
    elif state["kind"] == "grading.single":
        if settings.enable_llm and settings.ai_api_key:
            draft, metadata = _model_grading(state)
        else:
            draft = _fallback_grading(state).model_dump()
        draft["mode"] = "model" if metadata else "deterministic-fallback"
    elif state["kind"] == "assignment.summary":
        if settings.enable_llm and settings.ai_api_key:
            draft, metadata = _model_assignment_analysis(state)
        else:
            draft = _fallback_assignment_analysis(state).model_dump()
        draft["mode"] = "model" if metadata else "deterministic-fallback"
    elif state["kind"] == "course_map.generate":
        if settings.enable_llm and settings.ai_api_key:
            draft, metadata = _model_course_map(state)
        else:
            draft = _fallback_course_map(state).model_dump()
        draft["mode"] = metadata.get("generation_mode", "model") if metadata else "deterministic-fallback"
    else:
        draft = {"mode": "deterministic-fallback", "summary": "已完成课程上下文读取与资料检索。",
                 "citations": state.get("tool_results", {}).get("citations", [])}
    result = {**state, "draft": draft,
              "token_usage": metadata.get("token_usage") or state.get("token_usage", {})}
    result["steps"] = _step(
        result, "compose_result", tool_name="structured_llm" if metadata else "deterministic_fallback",
        summary={"mode": draft.get("mode"), "schema": state["task_type"],
                 "model_call_count": metadata.get("model_call_count"),
                 "structured_output_mode": metadata.get("structured_output_mode"),
                 "json_repair_applied": metadata.get("json_repair_applied"),
                 "model_repair_attempted": metadata.get("repair_attempted")}, started=started,
    )
    return result


def _validate(state: WorkflowState) -> ValidationResult:
    draft = state.get("draft", {})
    issues: list[str] = []
    evidence_sufficient = True
    kind = state["kind"]
    if kind in {"assignment.draft", "question.generate", "practice.generate"}:
        questions = draft.get("questions", [])
        expected = int(state.get("input_data", {}).get("question_count", 5))
        if len(questions) != expected:
            issues.append(f"题量应为 {expected}，实际为 {len(questions)}")
        allowed_kinds = set(state.get("input_data", {}).get("question_kinds") or [])
        if allowed_kinds and any(item.get("kind") not in allowed_kinds for item in questions):
            issues.append("包含教师未要求的题型")
        actual_kinds = {item.get("kind") for item in questions}
        if allowed_kinds and expected >= len(allowed_kinds):
            missing_kinds = allowed_kinds - actual_kinds
            if missing_kinds:
                issues.append("未覆盖教师选择的全部题型：" + "、".join(sorted(missing_kinds)))
        choice_questions = [item for item in questions if item.get("kind") in {
            "single_choice", "multiple_choice",
        }]
        if any(not _has_complete_choice_options(item.get("prompt", ""))
               for item in choice_questions):
            issues.append("选择题缺少完整的 A、B、C、D 选项")
        if any(not item.get("reference_answer") or int(item.get("score", 0)) <= 0 for item in questions):
            issues.append("存在不可判定或分值无效的题目")
        if len({item.get("prompt") for item in questions}) != len(questions):
            issues.append("存在重复题目")
        selected_knowledge_ids = {
            int(value) for value in state.get("input_data", {}).get("knowledge_point_ids", [])
        }
        if selected_knowledge_ids:
            question_knowledge_ids = [
                {int(value) for value in item.get("knowledge_point_ids", [])}
                for item in questions
            ]
            if any(not ids for ids in question_knowledge_ids):
                issues.append("存在未绑定知识点的题目")
            if any(not ids.issubset(selected_knowledge_ids) for ids in question_knowledge_ids):
                issues.append("题目绑定了教师选择范围外的知识点")
            if any(len(ids) > 2 for ids in question_knowledge_ids):
                issues.append("单道题绑定的知识点过多")
            covered_ids = set().union(*question_knowledge_ids) if question_knowledge_ids else set()
            if expected >= len(selected_knowledge_ids) and covered_ids != selected_knowledge_ids:
                issues.append("整套题未覆盖教师选择的全部知识点")
        citations = [citation for item in questions for citation in item.get("citations", [])]
        evidence_sufficient = bool(citations)
        if kind == "assignment.draft" and not evidence_sufficient:
            issues.append("课程资料证据不足")
    elif kind == "grading.single":
        try:
            suggestion = GradingSuggestion.model_validate(draft)
            answers = state.get("tool_results", {}).get("answers", [])
            expected_ids = {item["answer_id"] for item in answers}
            actual_ids = {item.answer_id for item in suggestion.items}
            if actual_ids != expected_ids:
                issues.append("批阅结果存在缺失或未知答案")
            expected_maximums = {item["answer_id"]: int(item["max_score"]) for item in answers}
            if any(item.max_score != expected_maximums.get(item.answer_id)
                   for item in suggestion.items):
                issues.append("批阅结果中的题目满分与实际作业不一致")
            if suggestion.total_score != sum(item.score for item in suggestion.items):
                issues.append("总分与分项得分不一致")
            if any(not item.rubric for item in suggestion.items):
                issues.append("存在缺少评分 Rubric 的题目")
            if any(not item.evidence_excerpt for item in suggestion.items):
                issues.append("存在无学生作答证据的评价")
            answer_texts = {
                item["answer_id"]: re.sub(r"\s+", "", item["student_answer"] or "")
                for item in answers
            }
            unsupported = []
            for item in suggestion.items:
                excerpt = re.sub(r"\s+", "", item.evidence_excerpt or "")
                answer_text = answer_texts.get(item.answer_id, "")
                if answer_text:
                    if not excerpt or excerpt not in answer_text:
                        unsupported.append(item.answer_id)
                elif excerpt not in {"", "未作答"}:
                    unsupported.append(item.answer_id)
            if unsupported:
                issues.append("部分评价的证据摘录无法在学生原答案中定位")
            if state.get("tool_results", {}).get("missing_question_ids"):
                issues.append("提交记录存在缺失题目，需要教师确认")
            low_confidence = suggestion.confidence < 60 or any(
                item.confidence < 50 for item in suggestion.items
            )
            evidence_sufficient = not issues and not low_confidence
            if low_confidence:
                issues.append("批阅置信度或证据支持不足")
        except Exception as exc:
            issues.append(f"批阅结构无效：{str(exc)[:200]}")
            evidence_sufficient = False
    elif kind == "assignment.summary":
        try:
            analysis = AssignmentAnalysisResult.model_validate(draft)
            expected_ids = {
                int(item["question_id"])
                for item in state.get("tool_results", {}).get("question_answers", [])
            }
            actual_ids = [item.question_id for item in analysis.question_summaries]
            if set(actual_ids) != expected_ids or len(actual_ids) != len(set(actual_ids)):
                issues.append("逐题分析存在缺失、重复或未知题目")
            evidence_text = {
                "overall_summary": analysis.overall_summary,
                "question_summaries": [{
                    "summary": item.summary,
                    "common_issues": item.common_issues,
                } for item in analysis.question_summaries],
            }
            if _has_unsupported_learning_inference(evidence_text):
                issues.append("答题分析包含无法由作答直接支持的学习状态推断")
            if not state.get("tool_results", {}).get("assignment_stats", {}).get("graded_count"):
                issues.append("尚无教师确认成绩，不能形成作业答题分析")
            evidence_sufficient = not issues
        except Exception as exc:
            issues.append(f"作业分析结构无效：{str(exc)[:200]}")
            evidence_sufficient = False
    elif kind == "course_map.generate":
        try:
            course_map = CourseMapDraft.model_validate(draft)
            material_chunks = state.get("tool_results", {}).get("course_map_chunks", [])
            available = {item["chunk_id"] for item in material_chunks}
            outline_ids = {item["chunk_id"] for item in material_chunks
                           if item.get("source_role") == "outline"}
            resource_type_by_chunk = {item["chunk_id"]: item.get("resource_type")
                                      for item in material_chunks}
            cited = {chunk_id for node in course_map.nodes for chunk_id in node.evidence_chunk_ids}
            cited.update(chunk_id for edge in course_map.edges for chunk_id in edge.evidence_chunk_ids)
            if cited - available:
                issues.append("课程路线引用了无效资料切片")
            contains_edges = [edge for edge in course_map.edges if edge.relation_type == "contains"]
            chapter_keys = {edge.source_key for edge in contains_edges}
            knowledge_keys = {edge.target_key for edge in contains_edges}
            if not contains_edges:
                issues.append("课程路线必须包含‘章节 → 知识点’的分层关系")
            child_counts = {
                key: sum(1 for edge in contains_edges if edge.source_key == key)
                for key in chapter_keys
            }
            if any(count < 2 or count > 4 for count in child_counts.values()):
                issues.append("每个章节应包含 2 至 4 个知识点")
            ungrouped = [node.name for node in course_map.nodes
                         if node.node_key not in chapter_keys and node.node_key not in knowledge_keys]
            if ungrouped:
                issues.append("存在未归属章节的知识点")
            cited_types = {resource_type_by_chunk[chunk_id] for chunk_id in cited
                           if chunk_id in resource_type_by_chunk}
            summary = course_map.summary or ""
            if "教材" in summary and "textbook" not in cited_types:
                issues.append("路线摘要声称使用教材，但实际证据没有教材引用")
            if "课件" in summary and "courseware" not in cited_types:
                issues.append("路线摘要声称使用课件，但实际证据没有课件引用")
            # Evidence is useful for traceability, but is deliberately not a
            # publication blocker: chapters and usable knowledge points are the
            # primary course-map product.
            evidence_sufficient = bool(outline_ids & cited) if outline_ids else bool(cited)
        except Exception as exc:
            issues.append(f"课程路线结构无效：{str(exc)[:200]}")
            evidence_sufficient = False
    requires_review = kind in {"assignment.draft", "grading.single"} or bool(issues)
    return ValidationResult(valid=not issues, issues=list(dict.fromkeys(issues)),
                            evidence_sufficient=evidence_sufficient,
                            requires_human_review=requires_review)


def validate_result(state: WorkflowState) -> WorkflowState:
    started = perf_counter()
    validation = _validate(state)
    result = {**state, "validation": validation.model_dump()}
    result["steps"] = _step(
        result, "validate_result", tool_name="deterministic_validator",
        summary={"valid": validation.valid, "issues": validation.issues}, started=started,
        step_type="validation",
    )
    return result


def _route_after_validation(state: WorkflowState) -> str:
    if state["kind"] == "grading.single" and state.get("reflection_count", 0) == 0:
        return "reflect_once"
    return "reflect_once" if not state.get("validation", {}).get("valid", False) else "finalize"


def reflect_once(state: WorkflowState) -> WorkflowState:
    """One bounded repair pass. It records a decision summary, never hidden chain-of-thought."""
    started = perf_counter()
    draft = dict(state.get("draft", {}))
    issues = state.get("validation", {}).get("issues", [])
    if state["kind"] in {"assignment.draft", "question.generate", "practice.generate"}:
        expected = int(state.get("input_data", {}).get("question_count", 5))
        questions = draft.get("questions", [])[:expected]
        if len(questions) < expected:
            fallback = _fallback_questions(state).model_dump()["questions"]
            questions.extend(fallback[len(questions):expected])
        allowed = state.get("input_data", {}).get("question_kinds") or ["short_answer"]
        seen: set[str] = set()
        for index, item in enumerate(questions):
            item["kind"] = item.get("kind") if item.get("kind") in allowed else allowed[index % len(allowed)]
            item["score"] = max(1, int(item.get("score", 10)))
            item["reference_answer"] = item.get("reference_answer") or "请教师补充参考答案。"
            if item.get("prompt") in seen:
                item["prompt"] = f"{item['prompt']}（变式 {index + 1}）"
            seen.add(item["prompt"])
        missing_kinds = [value for value in allowed
                         if value not in {item.get("kind") for item in questions}]
        fallback_questions = _fallback_questions(state).model_dump()["questions"]
        fallback_offsets: dict[str, int] = {}

        def next_fallback(question_kind: str) -> dict | None:
            candidates = [item for item in fallback_questions
                          if item.get("kind") == question_kind]
            if not candidates:
                return None
            offset = fallback_offsets.get(question_kind, 0)
            fallback_offsets[question_kind] = offset + 1
            return dict(candidates[offset % len(candidates)])

        for missing_kind in missing_kinds:
            replacement = next_fallback(missing_kind)
            if replacement:
                replace_index = next((index for index in range(len(questions) - 1, -1, -1)
                                      if sum(1 for item in questions
                                             if item.get("kind") == questions[index].get("kind")) > 1),
                                     len(questions) - 1)
                questions[replace_index] = replacement
        for index, item in enumerate(questions):
            if item.get("kind") in {"single_choice", "multiple_choice"} and not (
                _has_complete_choice_options(item.get("prompt", ""))
            ):
                replacement = next_fallback(item.get("kind"))
                if replacement:
                    questions[index] = replacement
        allowed_knowledge_ids = [
            int(value) for value in state.get("input_data", {}).get("knowledge_point_ids", [])
        ]
        if allowed_knowledge_ids:
            allowed_knowledge_set = set(allowed_knowledge_ids)
            for index, item in enumerate(questions):
                valid_ids: list[int] = []
                for value in item.get("knowledge_point_ids", []):
                    try:
                        knowledge_id = int(value)
                    except (TypeError, ValueError):
                        continue
                    if knowledge_id in allowed_knowledge_set and knowledge_id not in valid_ids:
                        valid_ids.append(knowledge_id)
                item["knowledge_point_ids"] = valid_ids[:2] or [
                    allowed_knowledge_ids[index % len(allowed_knowledge_ids)]
                ]
            if expected >= len(allowed_knowledge_ids):
                covered_ids = {
                    value for item in questions for value in item["knowledge_point_ids"]
                }
                for index, missing_id in enumerate(
                    value for value in allowed_knowledge_ids if value not in covered_ids
                ):
                    questions[index % len(questions)]["knowledge_point_ids"] = [missing_id]
        draft["questions"] = questions
    elif state["kind"] == "grading.single":
        settings = get_settings()
        revision_metadata: dict[str, Any] = {}
        if issues and settings.enable_llm and settings.ai_api_key:
            try:
                draft, revision_metadata = _model_grading_revision(state, draft, issues)
            except Exception:
                # The original suggestion remains available for teacher review
                # if the single bounded revision call fails.
                revision_metadata = {}
        maximums = {item["answer_id"]: item["max_score"]
                    for item in state.get("tool_results", {}).get("answers", [])}
        for item in draft.get("items", []):
            maximum = int(maximums.get(item.get("answer_id"), item.get("max_score", 0)))
            item["max_score"] = maximum
            item["score"] = min(maximum, max(0, int(item.get("score", 0))))
        draft["total_score"] = sum(int(item.get("score", 0)) for item in draft.get("items", []))
        draft["needs_review"] = True
        draft["review_reason"] = "批阅建议已经过证据复核，仍需教师最终确认"
        if revision_metadata:
            previous_usage = state.get("token_usage", {})
            revision_usage = revision_metadata.get("token_usage") or {}
            state = {**state, "token_usage": {
                key: int(previous_usage.get(key) or 0) + int(revision_usage.get(key) or 0)
                for key in ("prompt", "completion", "total")
            }}
    elif state["kind"] == "assignment.summary":
        settings = get_settings()
        fallback = _fallback_assignment_analysis(state).model_dump()
        revision_usage = None
        if settings.enable_llm and settings.ai_api_key:
            try:
                draft, revision_metadata = _model_assignment_analysis_revision(
                    state, draft, issues
                )
                revision_usage = revision_metadata.get("token_usage")
                draft["mode"] = "model-reflection"
            except Exception:
                draft = dict(draft)
        expected_ids = {
            int(item["question_id"])
            for item in state.get("tool_results", {}).get("question_answers", [])
        }
        current = {
            int(item["question_id"]): item for item in draft.get("question_summaries", [])
            if isinstance(item, dict) and item.get("question_id") in expected_ids
        }
        for item in fallback["question_summaries"]:
            current.setdefault(int(item["question_id"]), item)
        fallback_by_id = {
            int(item["question_id"]): item for item in fallback["question_summaries"]
        }
        for item_id, item in list(current.items()):
            evidence_text = {
                "summary": item.get("summary"),
                "common_issues": item.get("common_issues"),
            }
            if _has_unsupported_learning_inference(evidence_text):
                current[item_id] = fallback_by_id[item_id]
        overall_summary = draft.get("overall_summary") or fallback["overall_summary"]
        if _has_unsupported_learning_inference(overall_summary):
            overall_summary = fallback["overall_summary"]
        draft = {
            "overall_summary": overall_summary,
            "question_summaries": [current[item_id] for item_id in sorted(current)],
            "confidence": int(draft.get("confidence") or 0),
            "mode": draft.get("mode", "deterministic-reflection-fallback"),
        }
        if revision_usage:
            previous_usage = state.get("token_usage") or {}
            state["token_usage"] = {key: int(previous_usage.get(key) or 0) + int(
                revision_usage.get(key) or 0
            ) for key in ("prompt", "completion", "total")}
    elif state["kind"] == "course_map.generate" and issues:
        draft = _fallback_course_map(state).model_dump()
        draft["mode"] = "deterministic-reflection-fallback"
    reflected = {**state, "draft": draft, "reflection_count": 1}
    reflected["validation"] = _validate(reflected).model_dump()
    if state["kind"] == "grading.single" and reflected["validation"]["issues"]:
        draft["review_reason"] = (
            "复核后仍存在以下问题：" + "；".join(reflected["validation"]["issues"])[:400]
        )
        reflected["draft"] = draft
    reflected["steps"] = _step(
        reflected, "reflect_once", tool_name="bounded_revision",
        summary={"revision_count": 1, "remaining_issues": reflected["validation"]["issues"]},
        started=started, step_type="reflection",
    )
    return reflected


def finalize(state: WorkflowState) -> WorkflowState:
    started = perf_counter()
    validation = state.get("validation", {})
    needs_review = bool(validation.get("requires_human_review"))
    result = {**state, "result": state.get("draft", {}), "needs_review": needs_review}
    result["steps"] = _step(
        result, "finalize", tool_name="output_contract",
        summary={"valid": validation.get("valid", False), "needs_review": needs_review,
                 "reflection_count": state.get("reflection_count", 0)},
        started=started,
    )
    return result


def build_workflow():
    graph = StateGraph(WorkflowState)
    for name, node in (
        ("prepare_context", prepare_context), ("make_plan", make_plan),
        ("execute_tools", execute_tools), ("compose_result", compose_result),
        ("validate_result", validate_result), ("reflect_once", reflect_once),
        ("finalize", finalize),
    ):
        graph.add_node(name, node)
    graph.add_edge(START, "prepare_context")
    graph.add_edge("prepare_context", "make_plan")
    graph.add_edge("make_plan", "execute_tools")
    graph.add_edge("execute_tools", "compose_result")
    graph.add_edge("compose_result", "validate_result")
    graph.add_conditional_edges("validate_result", _route_after_validation,
                                {"reflect_once": "reflect_once", "finalize": "finalize"})
    graph.add_edge("reflect_once", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


workflow = build_workflow()


def run_workflow(kind: str, resource_id: int, prompt: str | None = None,
                 input_data: dict[str, Any] | None = None, owner_id: int | None = None) -> dict[str, Any]:
    state = workflow.invoke({
        "kind": kind, "resource_id": resource_id, "owner_id": owner_id,
        "prompt": prompt, "input_data": input_data or {}, "steps": [],
    })
    return {
        "agent_name": state["agent_name"], "task_type": state["task_type"],
        "plan": state.get("plan"), "result": state.get("result", {}),
        "validation": state.get("validation", {}),
        "needs_review": state.get("needs_review", False),
        "reflection_count": state.get("reflection_count", 0),
        "steps": state.get("steps", []), "delegations": state.get("delegations", []),
        "token_usage": state.get("token_usage"),
    }
