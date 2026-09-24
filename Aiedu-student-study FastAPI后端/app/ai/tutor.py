from __future__ import annotations

import json
import re
from time import perf_counter

from sqlalchemy.orm import Session

from app.ai.contracts import (
    AgentPlan, Citation, PlanStep, StudentLearningBrief, TutorAnswer, ValidationResult,
)
from app.core.config import get_settings
from app.integrations.ai_provider import structured_completion
from app.integrations.rag import search_course
from app.integrations.web_search import web_search
from app.models import Course, CourseOffering, User
from app.services.learning import profile_view


PERSONAL_IDENTITY_MARKERS = ("我是谁", "我的名字", "我叫什么", "认识我", "知道我是谁")
PROFILE_MARKERS = (
    "我的学情", "学习画像", "我的掌握", "掌握情况", "薄弱", "暂无学习记录",
    "复习计划", "怎么复习", "如何复习", "适合我", "根据我的", "结合我的", "个性化", "诊断练习",
)
SELF_REFERENCES = ("我", "自己")
LEARNING_DIFFICULTY_MARKERS = (
    "不会", "不懂", "没掌握", "总是错", "总是出错", "经常错", "经常出错", "老是错", "老是出错",
    "容易错", "容易出错", "跟不上", "记不住", "做不好", "困难", "卡在",
)
PROFILE_FOLLOWUP_MARKERS = ("具体呢", "为什么呢", "怎么改善", "怎么提高", "哪些方面", "然后呢", "接下来呢")
CURRENT_MARKERS = ("今天", "最新", "当前", "新闻", "现在发生", "实时")
RESOURCE_MARKERS = ("哪一页", "哪个课件", "资料里", "出处", "定位")
GREETING_WORDS = {"你好", "您好", "嗨", "哈喽", "hello", "hi", "hey", "在吗"}


def _is_greeting(question: str) -> bool:
    normalized = "".join(question.split()).strip("，。！？!?~～.").lower()
    return normalized in GREETING_WORDS


def _is_personal_identity(question: str) -> bool:
    normalized = "".join(question.split())
    return any(marker in normalized for marker in PERSONAL_IDENTITY_MARKERS)


def _contains_profile_signal(text: str) -> bool:
    normalized = "".join(text.split())
    if _is_personal_identity(normalized) or any(marker in normalized for marker in PROFILE_MARKERS):
        return True
    return (any(marker in normalized for marker in SELF_REFERENCES)
            and any(marker in normalized for marker in LEARNING_DIFFICULTY_MARKERS))


def _needs_learning_profile(question: str, conversation_memory: dict | None) -> bool:
    if _contains_profile_signal(question):
        return True
    normalized = "".join(question.split()).strip("，。！？!?~～.")
    if len(normalized) > 16 or not any(marker in normalized for marker in PROFILE_FOLLOWUP_MARKERS):
        return False
    recent = (conversation_memory or {}).get("recent_messages", [])
    recent_user_messages = [item.get("content", "") for item in recent if item.get("role") == "user"]
    return any(_contains_profile_signal(item) for item in recent_user_messages[-2:])


def _citation(row: dict) -> dict:
    return Citation(
        chunk_id=row.get("chunk_id"), resource_id=int(row["resource_id"]),
        title=row.get("title") or "课程资料", position=int(row.get("position", 0)),
        page_number=row.get("page_number"), slide_number=row.get("slide_number"),
        heading_path=row.get("heading_path"), excerpt=(row.get("text") or "")[:1200],
        score=row.get("rerank_score", row.get("score")),
    ).model_dump()


def _point_relevance(name: str, question: str) -> int:
    normalized_name = re.sub(r"\s+", "", name)
    normalized_question = re.sub(r"\s+", "", question)
    if normalized_name in normalized_question:
        return 100
    return max((len(piece) for piece in (
        normalized_name[index:index + 2] for index in range(max(0, len(normalized_name) - 1))
    ) if piece in normalized_question), default=0)


def _learning_brief(db: Session, student_id: int, offering_id: int, question: str = "") -> dict:
    student = db.get(User, student_id)
    offering = db.get(CourseOffering, offering_id)
    course = db.get(Course, offering.course_id) if offering else None
    profile = profile_view(db, student_id, offering_id)
    points = profile.get("knowledge_points", [])
    weak = [item["name"] for item in points if item["state"] == "weak"]
    unobserved = [item["name"] for item in points if item["state"] == "unobserved"]
    mastered = [item["name"] for item in points if item["state"] == "mastered"]
    actions = ([f"先复习 {name}" for name in weak[:5]] or
               (["完成一次综合巩固练习"] if mastered else
                ["先完成一次课程基础练习，建立初始学习记录"]))
    state_order = {"weak": 0, "mastered": 1, "unobserved": 2}
    detail_rows = sorted(points, key=lambda item: (
        -_point_relevance(item["name"], question), state_order.get(item["state"], 3),
        item.get("mastery_score", 0),
    ))[:20]
    point_details = [{
        "name": item["name"], "chapter_name": item.get("chapter_name"),
        "state": item["state"], "mastery_score": item.get("mastery_score", 0),
        "recent_evidence": [
            f"{'作业' if evidence['source_type'] == 'assignment' else '诊断练习'} {evidence['score']} 分"
            for evidence in item.get("evidence", [])[:5]
        ],
    } for item in detail_rows]
    return StudentLearningBrief(
        summary=f"已掌握 {len(mastered)} 个，薄弱 {len(weak)} 个，暂无学习记录 {len(unobserved)} 个。",
        student_name=student.display_name if student else None,
        course_name=course.name if course else None,
        weak_points=weak[:20], unobserved_points=unobserved[:20], mastered_points=mastered[:20],
        recommended_actions=actions, point_details=point_details,
    ).model_dump()


def _profile_fallback_answer(brief: dict) -> str:
    details = brief.get("point_details") or []
    weak = [item for item in details if item.get("state") == "weak"]
    if weak:
        lines = []
        for item in weak[:3]:
            chapter = f"（{item['chapter_name']}）" if item.get("chapter_name") else ""
            evidence = "、".join(item.get("recent_evidence") or []) or "暂无可展示的近期得分"
            lines.append(f"{item['name']}{chapter}：掌握度 {item['mastery_score']}，依据为 {evidence}")
        return "根据你的学习画像，目前较薄弱的是：" + "；".join(lines) + "。"
    if details and all(item.get("state") == "unobserved" for item in details):
        return "当前还没有已评分的作业或练习记录，可以先完成一组课程基础练习。"
    return f"根据当前学习画像：{brief['summary']} " + "；".join(brief["recommended_actions"])


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
    identity_request = False
    if guided:
        intent = "assignment_guidance"
    elif _is_greeting(question):
        intent = "chitchat"
    elif _is_personal_identity(question):
        intent = "personalized_learning"
        identity_request = True
    elif _needs_learning_profile(question, conversation_memory):
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
    if not guided and intent != "chitchat" and not identity_request:
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
        learning_brief = _learning_brief(db, student_id, offering_id, question)
        delegations.append({
            "agent_name": "student_learning_assistant", "task_type": "student_learning_brief",
            "plan": AgentPlan(goal="为问答智能体提供最小必要的个人画像摘要", steps=[
                PlanStep(id="1", action="读取确定性学习画像", tool="get_student_mastery", reason="画像由业务证据计算"),
                PlanStep(id="2", action="整理薄弱、已掌握和暂无记录项", tool="get_learning_evidence", reason="只返回回答所需摘要"),
            ]).model_dump(),
            "result": learning_brief,
            "validation": ValidationResult(valid=True, evidence_sufficient=True).model_dump(),
            "steps": [{
                "node_name": "build_student_learning_brief",
                "agent_name": "student_learning_assistant", "step_type": "delegation",
                "tool_name": "get_student_mastery", "duration_ms": 0,
                "output_summary": {"weak_count": len(learning_brief["weak_points"]),
                                   "unobserved_count": len(learning_brief["unobserved_points"]),
                                   "detail_count": len(learning_brief["point_details"])},
            }],
        })
    if not guided and intent != "chitchat" and not identity_request:
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
    model_fallback = False
    if guided:
        answer = TutorAnswer(
            intent="assignment_guidance",
            answer=("这道题与当前开放作业高度相似，请认真做题哟。"
                    "我不能直接给出答案；你可以先写出自己的思路或第一步尝试，我再给你提示。"),
            policy_mode="guided", evidence_sufficient=True,
        )
    elif intent == "chitchat":
        answer = TutorAnswer(
            intent="chitchat",
            answer="你好呀，我是问答杏台。你可以问我课程知识、资料位置，也可以让我结合你的学情制定复习建议。",
            evidence_sufficient=True,
        )
    elif identity_request and learning_brief:
        student_name = learning_brief.get("student_name") or "当前登录的同学"
        course_name = learning_brief.get("course_name")
        course_text = f"，你当前正在学习《{course_name}》" if course_name else ""
        answer = TutorAnswer(
            intent="personalized_learning",
            answer=(f"当然知道，你是{student_name}{course_text}。"
                    "我刚刚通过学生学习助手读取了你的个人学习画像；"
                    "如果你愿意，我还可以结合你的掌握情况分析薄弱点或制定复习计划。"),
            used_learning_profile=True, evidence_sufficient=True,
        )
    elif get_settings().enable_llm and get_settings().ai_api_key:
        try:
            answer, metadata = structured_completion(
                TutorAnswer,
                system_prompt=("你是 AIedu 学生问答智能体。只能依据给定课程资料和可选的个人画像摘要回答；"
                               "涉及学生个人情况时，必须优先使用 learning_brief 中的掌握度与成绩记录，"
                               "不得把个人画像误称为课程资料。有学习成绩时必须直接按画像判断；"
                               "只有完全没有已评分记录时才说明暂无学习记录。课程资料必须支持结论。"
                               "不要向学生展示‘证据不足、无依据、置信度、检索失败’等内部技术判断；"
                               "资料未涵盖问题时，只需自然说明当前课程资料暂未包含相关内容。"
                               "开放作业只做苏格拉底式引导。"),
                user_prompt=json.dumps({"question": question, "intent": intent,
                                        "citations": citations, "learning_brief": learning_brief,
                                        "conversation_memory": conversation_memory or {}},
                                       ensure_ascii=False, default=str),
            )
            token_usage = metadata.get("token_usage") or token_usage
        except Exception:
            if intent != "personalized_learning" or not learning_brief:
                raise
            model_fallback = True
            answer = TutorAnswer(
                intent="personalized_learning", answer=_profile_fallback_answer(learning_brief),
                citations=[Citation.model_validate(item) for item in citations],
                used_learning_profile=True, evidence_sufficient=True,
            )
    elif intent == "personalized_learning" and learning_brief:
        answer = TutorAnswer(
            intent="personalized_learning",
            answer=_profile_fallback_answer(learning_brief),
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
            answer=("当前课程资料暂未包含这个问题的相关内容。"
                    "你可以换一种问法，或请教师补充相关资料。"),
            evidence_sufficient=False,
        )
    steps.append(_step("compose_result", "structured_llm" if token_usage["total"] else "deterministic_fallback",
                       compose_started, {"intent": intent, "policy_mode": answer.policy_mode,
                                         "model_fallback": model_fallback}))

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
