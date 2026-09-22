from __future__ import annotations

import json
from time import perf_counter

from sqlalchemy.orm import Session

from app.ai.contracts import (
    AgentPlan, Citation, PlanStep, StudentLearningBrief, TutorAnswer, ValidationResult,
)
from app.core.config import get_settings
from app.integrations.ai_provider import structured_completion
from app.integrations.rag import search_course
from app.integrations.web_search import web_search
from app.services.learning import profile_view


PERSONAL_MARKERS = ("我的", "我哪里", "薄弱", "学情", "掌握", "怎么复习", "如何复习", "复习计划", "适合我")
CURRENT_MARKERS = ("今天", "最新", "当前", "新闻", "现在发生", "实时")
RESOURCE_MARKERS = ("哪一页", "哪个课件", "资料里", "出处", "定位")


def _citation(row: dict) -> dict:
    return Citation(
        chunk_id=row.get("chunk_id"), resource_id=int(row["resource_id"]),
        title=row.get("title") or "课程资料", position=int(row.get("position", 0)),
        page_number=row.get("page_number"), slide_number=row.get("slide_number"),
        heading_path=row.get("heading_path"), excerpt=(row.get("text") or "")[:1200],
        score=row.get("rerank_score", row.get("score")),
    ).model_dump()


def _learning_brief(db: Session, student_id: int, offering_id: int) -> dict:
    profile = profile_view(db, student_id, offering_id)
    points = profile.get("knowledge_points", [])
    weak = [item["name"] for item in points if item["state"] == "weak"]
    insufficient = [item["name"] for item in points if item["state"] == "insufficient_data"]
    mastered = [item["name"] for item in points if item["state"] == "mastered"]
    actions = ([f"先复习 {name}" for name in weak[:5]] or
               [f"先用诊断练习补充 {name} 的学习证据" for name in insufficient[:5]] or
               ["完成一次综合巩固练习"])
    return StudentLearningBrief(
        summary=f"已掌握 {len(mastered)} 个，薄弱 {len(weak)} 个，证据不足 {len(insufficient)} 个。",
        weak_points=weak, insufficient_points=insufficient, mastered_points=mastered,
        recommended_actions=actions,
    ).model_dump()


def _step(name: str, tool: str | None, started: float, summary: dict, step_type: str = "node") -> dict:
    return {
        "node_name": name, "agent_name": "student_qa_agent", "step_type": step_type,
        "tool_name": tool, "output_summary": summary,
        "duration_ms": round((perf_counter() - started) * 1000),
    }


def run_student_qa(
    db: Session, *, student_id: int, offering_id: int, question: str,
    guided: bool, matched_assignment_id: int | None, similarity: float,
    conversation_memory: dict | None = None,
) -> dict:
    """A bounded Student QA run with conditional learning-agent delegation."""
    steps: list[dict] = []
    started = perf_counter()
    if guided:
        intent = "assignment_guidance"
    elif any(marker in question for marker in PERSONAL_MARKERS):
        intent = "personalized_learning"
    elif any(marker in question for marker in CURRENT_MARKERS):
        intent = "current_web"
    elif any(marker in question for marker in RESOURCE_MARKERS):
        intent = "resource_lookup"
    else:
        intent = "course_qa"
    steps.append(_step("prepare_context", "open_assignment_similarity", started, {
        "guided": guided, "similarity": round(similarity, 4), "intent": intent,
        "memory_messages": len((conversation_memory or {}).get("recent_messages", [])),
    }))

    plan_started = perf_counter()
    plan_steps = [
        PlanStep(id="1", action="检查开放作业相似度并识别问题类型",
                 tool="open_assignment_similarity", reason="先执行防抄策略并确定所需证据"),
    ]
    if intent == "personalized_learning":
        plan_steps.append(PlanStep(id="2", action="委派学生学习助手读取精简画像",
                                   tool="delegate_student_learning_assistant", reason="问题明确要求结合个人情况"))
    if not guided:
        plan_steps.append(PlanStep(id=str(len(plan_steps) + 1), action="检索课程资料",
                                   tool="search_course_materials", reason="以课程内证据回答"))
    plan_steps.append(PlanStep(id=str(len(plan_steps) + 1), action="生成回答并执行证据自检",
                               tool="validate_tutor_answer", reason="防止无依据回答或泄露作业答案"))
    plan = AgentPlan(goal=question, steps=plan_steps[:4]).model_dump()
    steps.append(_step("make_plan", None, plan_started, {"step_count": len(plan["steps"])}, "planning"))

    tool_started = perf_counter()
    citations: list[dict] = []
    used_web = False
    learning_brief = None
    delegations: list[dict] = []
    if intent == "personalized_learning":
        learning_brief = _learning_brief(db, student_id, offering_id)
        delegations.append({
            "agent_name": "student_learning_assistant", "task_type": "student_learning_brief",
            "plan": AgentPlan(goal="为问答智能体提供最小必要的个人画像摘要", steps=[
                PlanStep(id="1", action="读取确定性学习画像", tool="get_student_mastery", reason="画像由业务证据计算"),
                PlanStep(id="2", action="整理薄弱、已掌握和证据不足项", tool="get_learning_evidence", reason="只返回回答所需摘要"),
            ]).model_dump(),
            "result": learning_brief,
            "validation": ValidationResult(valid=True, evidence_sufficient=True).model_dump(),
            "steps": [{
                "node_name": "build_student_learning_brief",
                "agent_name": "student_learning_assistant", "step_type": "delegation",
                "tool_name": "get_student_mastery", "duration_ms": 0,
                "output_summary": {"weak_count": len(learning_brief["weak_points"]),
                                   "insufficient_count": len(learning_brief["insufficient_points"])},
            }],
        })
    if not guided:
        citations = [_citation(row) for row in search_course(offering_id, question, limit=6, db=db)]
        if intent == "current_web" and not citations and get_settings().tavily_api_key:
            citations = [Citation(
                resource_id=None, title=item["title"], position=index,
                excerpt=item["excerpt"], score=item.get("score"), url=item.get("url"),
                fetched_at=item.get("fetched_at"), source="web",
            ).model_dump() for index, item in enumerate(web_search(question), 1)]
            used_web = bool(citations)
    steps.append(_step("execute_tools", "bounded_tool_executor", tool_started, {
        "citation_count": len(citations), "delegation_count": len(delegations),
        "web_search": "used" if used_web else (
            "unavailable" if intent == "current_web" and not get_settings().tavily_api_key else "not_needed"),
    }, "tool"))

    compose_started = perf_counter()
    token_usage = {"prompt": 0, "completion": 0, "total": 0}
    if guided:
        answer = TutorAnswer(
            intent="assignment_guidance",
            answer=("这段提问与当前开放作业高度相关，我不能直接给出答案。"
                    "请先写出你已确定的条件、目标和第一步尝试，我会根据你的思路给出下一层提示。"),
            policy_mode="guided", evidence_sufficient=True,
        )
    elif get_settings().enable_llm and get_settings().ai_api_key:
        answer, metadata = structured_completion(
            TutorAnswer,
            system_prompt=("你是 AIedu 学生问答智能体。只能依据给定课程证据和可选的个人画像摘要回答；"
                           "引用必须支持结论。证据不足时要明确说明。开放作业只做苏格拉底式引导。"),
            user_prompt=json.dumps({"question": question, "intent": intent,
                                    "citations": citations, "learning_brief": learning_brief,
                                    "conversation_memory": conversation_memory or {}},
                                   ensure_ascii=False, default=str),
        )
        token_usage = metadata.get("token_usage") or token_usage
    elif intent == "personalized_learning" and learning_brief:
        answer = TutorAnswer(
            intent="personalized_learning",
            answer=f"根据当前学习画像：{learning_brief['summary']} " + "；".join(learning_brief["recommended_actions"]),
            citations=[Citation.model_validate(item) for item in citations],
            used_learning_profile=True, evidence_sufficient=True,
        )
    elif citations:
        first = citations[0]
        locator = f"第 {first['page_number']} 页" if first.get("page_number") else (
            f"第 {first['slide_number']} 张幻灯片" if first.get("slide_number") else "相关段落")
        source_label = "网页资料" if first.get("source") == "web" else "课程资料"
        answer = TutorAnswer(
            intent=intent if intent != "current_web" else "current_web",
            answer=f"根据{source_label}《{first['title']}》{locator}，可以先这样理解：{first['excerpt'][:500]}",
            citations=[Citation.model_validate(item) for item in citations],
            used_web_search=used_web, evidence_sufficient=True,
        )
    else:
        answer = TutorAnswer(
            intent=intent if intent != "current_web" else "current_web",
            answer=("当前课程资料中没有检索到足够证据。"
                    "网页搜索也未配置或不适合替代课程依据；你可以换一种问法，或请教师补充相关资料。"),
            evidence_sufficient=False,
        )
    steps.append(_step("compose_result", "structured_llm" if token_usage["total"] else "deterministic_fallback",
                       compose_started, {"intent": intent, "policy_mode": answer.policy_mode}))

    validation_started = perf_counter()
    issues = []
    if guided and answer.policy_mode != "guided":
        issues.append("开放作业回答未进入引导模式")
    if answer.citations and not citations:
        issues.append("回答包含无法验证的引用")
    if not answer.answer.strip():
        issues.append("回答为空")
    validation = ValidationResult(
        valid=not issues, issues=issues,
        evidence_sufficient=answer.evidence_sufficient,
        requires_human_review=False,
    )
    steps.append(_step("validate_result", "evidence_self_check", validation_started,
                       {"valid": validation.valid, "evidence_sufficient": validation.evidence_sufficient},
                       "validation"))
    steps.append(_step("finalize", "output_contract", perf_counter(),
                       {"used_learning_profile": answer.used_learning_profile,
                        "delegation_count": len(delegations)}))
    return {
        "agent_name": "student_qa_agent", "task_type": intent, "plan": plan,
        "result": answer.model_dump(), "validation": validation.model_dump(),
        "needs_review": False, "reflection_count": 0, "steps": steps,
        "delegations": delegations, "token_usage": token_usage,
        "matched_assignment_id": matched_assignment_id,
    }
