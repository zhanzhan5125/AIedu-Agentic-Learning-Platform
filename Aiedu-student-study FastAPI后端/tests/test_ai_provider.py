from __future__ import annotations

from types import SimpleNamespace

import openai
import pytest
from pydantic import BaseModel

from app.ai.contracts import AssignmentRoutingDecision, CourseMapDraft, TutorRoutingDecision
from app.ai import tutor, workflows
from app.integrations import ai_provider
from app.integrations.ai_provider import _json_payload
from app.schemas import AssignmentDraftRequest


def _login(client, role: str, account: str) -> str:
    response = client.post("/api/v1/auth/login", json={
        "role": role, "account": account, "password": "password123"
    })
    assert response.status_code == 200
    return response.json()["data"]["token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_ai_provider_status_is_authenticated_and_never_returns_key(client):
    assert client.get("/api/v1/ai/provider/status").status_code == 401
    token = _login(client, "manager", "admin")
    response = client.get("/api/v1/ai/provider/status", headers=_headers(token))
    assert response.status_code == 200
    data = response.json()["data"]
    assert "api_key" not in data
    assert data["embedding_model"] == "text-embedding-3-large"
    assert "grading" in data["business_endpoints"]


def test_ai_provider_probes_return_sanitized_results(client, monkeypatch):
    token = _login(client, "teacher", "teacher")
    monkeypatch.setattr("app.api.ai.chat_completion", lambda prompt: {
        "model": "deepseek-test", "content": prompt, "latency_ms": 10, "token_usage": None
    })
    monkeypatch.setattr("app.api.ai.embedding_probe", lambda text: {
        "model": "text-embedding-3-large", "dimensions": 3072,
        "latency_ms": 20, "vector_norm": 1.0,
    })
    chat = client.post("/api/v1/ai/provider/test-chat", headers=_headers(token), json={"prompt": "ping"})
    embedding = client.post(
        "/api/v1/ai/provider/test-embedding", headers=_headers(token), json={"text": "向量测试"}
    )
    assert chat.status_code == embedding.status_code == 200
    assert chat.json()["data"]["content"] == "ping"
    assert embedding.json()["data"]["dimensions"] == 3072


def test_course_map_confidence_is_clamped_to_contract_range():
    value = CourseMapDraft.model_validate({
        "title": "测试路线",
        "nodes": [{
            "node_key": "intro", "name": "课程导论", "confidence": -1,
            "evidence_chunk_ids": [1],
        }, {
            "node_key": "practice", "name": "课程实践", "confidence": 120,
            "evidence_chunk_ids": [2],
        }],
        "edges": [{
            "source_key": "intro", "target_key": "practice", "relation_type": "next",
            "confidence": -1, "evidence_chunk_ids": [1],
        }],
    })
    assert [node.confidence for node in value.nodes] == [0, 100]
    assert value.edges[0].confidence == 0


def test_json_payload_repairs_a_missing_comma_and_closing_brace():
    payload, repaired = _json_payload('{"name": "C语言" "count": 5')

    assert repaired is True
    assert payload == {"name": "C语言", "count": 5}


def test_json_payload_keeps_valid_json_unchanged():
    payload, repaired = _json_payload('{"name": "C语言", "count": 5}')

    assert repaired is False
    assert payload == {"name": "C语言", "count": 5}


def test_structured_completion_prefers_strict_json_schema(monkeypatch):
    class ProbeResult(BaseModel):
        name: str
        count: int

    captured: dict = {}

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content='{"name":"test","count":2}'),
                    finish_reason="stop",
                )],
                usage=None,
                model="deepseek-v3.2",
            )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions()),
    )
    monkeypatch.setattr(openai, "OpenAI", lambda **_kwargs: fake_client)
    monkeypatch.setattr(ai_provider, "get_settings", lambda: SimpleNamespace(
        enable_llm=True, ai_api_key="test", ai_base_url="https://example.test/v1",
        llm_model="deepseek-v3.2",
    ))

    value, metadata = ai_provider.structured_completion(
        ProbeResult, system_prompt="return json", user_prompt="test",
    )

    assert value == ProbeResult(name="test", count=2)
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert metadata["structured_output_mode"] == "json_schema"
    assert metadata["json_repair_applied"] is False


def test_student_qa_model_router_can_autonomously_delegate_learning_agent(monkeypatch):
    monkeypatch.setattr(tutor, "get_settings", lambda: SimpleNamespace(
        enable_llm=True, ai_api_key="test",
    ))
    monkeypatch.setattr(tutor, "structured_completion", lambda schema, **_kwargs: (
        TutorRoutingDecision(
            intent="personalized_learning",
            delegate_student_learning_assistant=True,
            search_course_materials=False,
            search_web=False,
            rationale="问题需要结合学生近期作业表现。",
        ),
        {"token_usage": {"prompt": 10, "completion": 5, "total": 15}},
    ) if schema is TutorRoutingDecision else (_ for _ in ()).throw(AssertionError(schema)))

    decision, metadata, mode = tutor._route_with_model(
        "结合最近的作业表现，接下来应该重点学什么？", None,
    )

    assert mode == "model"
    assert decision.intent == "personalized_learning"
    assert decision.delegate_student_learning_assistant is True
    assert decision.search_course_materials is False
    assert metadata["token_usage"]["total"] == 15


def test_student_qa_identity_postcondition_overrides_unstable_chitchat_route(monkeypatch):
    monkeypatch.setattr(tutor, "get_settings", lambda: SimpleNamespace(
        enable_llm=True, ai_api_key="test",
    ))
    monkeypatch.setattr(tutor, "structured_completion", lambda schema, **_kwargs: (
        TutorRoutingDecision(
            intent="chitchat",
            delegate_student_learning_assistant=False,
            search_course_materials=False,
            search_web=False,
            identity_request=False,
            rationale="误判为闲聊。",
        ),
        {"token_usage": {"prompt": 10, "completion": 5, "total": 15}},
    ) if schema is TutorRoutingDecision else (_ for _ in ()).throw(AssertionError(schema)))

    decision, _, mode = tutor._route_with_model("你知道我是谁吗？", None)

    assert mode == "model"
    assert decision.intent == "personalized_learning"
    assert decision.identity_request is True
    assert decision.delegate_student_learning_assistant is True
    assert decision.search_course_materials is False
    assert decision.search_web is False


def test_student_qa_identity_flag_is_not_inferred_from_any_first_person_question(monkeypatch):
    monkeypatch.setattr(tutor, "get_settings", lambda: SimpleNamespace(
        enable_llm=True, ai_api_key="test",
    ))
    monkeypatch.setattr(tutor, "structured_completion", lambda schema, **_kwargs: (
        TutorRoutingDecision(
            intent="personalized_learning",
            delegate_student_learning_assistant=True,
            search_course_materials=False,
            search_web=False,
            identity_request=True,
            rationale="需要读取个人画像。",
        ),
        {"token_usage": {}},
    ) if schema is TutorRoutingDecision else (_ for _ in ()).throw(AssertionError(schema)))

    decision, _, _ = tutor._route_with_model("我第一章哪些知识点最薄弱？", None)

    assert decision.intent == "personalized_learning"
    assert decision.delegate_student_learning_assistant is True
    assert decision.identity_request is False


def test_student_qa_current_web_fallback_does_not_duplicate_course_search():
    decision = tutor._fallback_routing("目前最新的 Clang 稳定版本是什么？", None)

    assert decision.intent == "current_web"
    assert decision.search_web is True
    assert decision.search_course_materials is False


def test_assignment_model_router_can_skip_course_agent_for_explicit_scope(monkeypatch):
    monkeypatch.setattr(workflows, "get_settings", lambda: SimpleNamespace(
        enable_llm=True, ai_api_key="test",
    ))
    monkeypatch.setattr(workflows, "structured_completion", lambda schema, **_kwargs: (
        AssignmentRoutingDecision(
            delegate_teacher_course_assistant=False,
            include_class_insights=False,
            search_course_materials=True,
            rationale="教师已明确选择章节和知识点，直接检索资料即可。",
        ),
        {"token_usage": {"prompt": 8, "completion": 4, "total": 12}},
    ) if schema is AssignmentRoutingDecision else (_ for _ in ()).throw(AssertionError(schema)))

    decision, metadata, mode = workflows._assignment_routing({
        "context": {"course": {"name": "程序设计"}},
        "input_data": {"selected_chapter_names": ["第一章"],
                       "knowledge_point_ids": [1, 2, 3]},
    })

    assert mode == "model"
    assert decision.delegate_teacher_course_assistant is False
    assert decision.search_course_materials is True
    assert metadata["token_usage"]["total"] == 12


def test_assignment_fallback_covers_selected_question_kinds():
    state = {
        "input_data": {
            "question_count": 4,
            "question_kinds": [
                "short_answer", "single_choice", "multiple_choice", "programming",
            ],
            "difficulty": 4,
            "keywords": ["循环"],
            "knowledge_point_ids": [1, 2],
        },
        "tool_results": {"course_context": {"citations": []}},
    }

    result = workflows._fallback_questions(state)

    assert [item.kind for item in result.questions] == [
        "short_answer", "single_choice", "multiple_choice", "programming",
    ]
    assert all(item.difficulty == 4 for item in result.questions)
    assert [item.knowledge_point_ids for item in result.questions] == [
        [1], [2], [1], [2],
    ]
    for item in result.questions[1:3]:
        assert workflows._has_complete_choice_options(item.prompt)


def test_assignment_validation_rejects_missing_selected_kind():
    state = {
        "kind": "assignment.draft",
        "input_data": {
            "question_count": 2,
            "question_kinds": ["short_answer", "programming"],
        },
        "draft": {
            "questions": [
                {
                    "kind": "short_answer", "prompt": "问题一", "reference_answer": "答案一",
                    "score": 10, "citations": [{"title": "资料", "excerpt": "依据"}],
                },
                {
                    "kind": "short_answer", "prompt": "问题二", "reference_answer": "答案二",
                    "score": 10, "citations": [{"title": "资料", "excerpt": "依据"}],
                },
            ],
        },
    }

    validation = workflows._validate(state)

    assert validation.valid is False
    assert any("未覆盖教师选择的全部题型" in issue for issue in validation.issues)


def test_assignment_validation_rejects_invalid_knowledge_point_mapping():
    state = {
        "kind": "assignment.draft",
        "input_data": {
            "question_count": 2,
            "question_kinds": ["short_answer"],
            "knowledge_point_ids": [1, 2],
        },
        "draft": {
            "questions": [
                {
                    "kind": "short_answer", "prompt": "问题一", "reference_answer": "答案一",
                    "score": 10, "knowledge_point_ids": [],
                    "citations": [{"title": "资料", "excerpt": "依据"}],
                },
                {
                    "kind": "short_answer", "prompt": "问题二", "reference_answer": "答案二",
                    "score": 10, "knowledge_point_ids": [3],
                    "citations": [{"title": "资料", "excerpt": "依据"}],
                },
            ],
        },
    }

    validation = workflows._validate(state)

    assert validation.valid is False
    assert any("未绑定知识点" in issue for issue in validation.issues)
    assert any("选择范围外" in issue for issue in validation.issues)
    assert any("未覆盖教师选择的全部知识点" in issue for issue in validation.issues)


def test_assignment_reflection_repairs_choice_options_without_duplicates():
    state = {
        "kind": "assignment.draft",
        "input_data": {
            "question_count": 2,
            "question_kinds": ["single_choice"],
            "keywords": ["数组"],
        },
        "tool_results": {"course_context": {"citations": []}},
        "draft": {
            "questions": [
                {"kind": "single_choice", "prompt": "不完整选择题一", "reference_answer": "A", "score": 10},
                {"kind": "single_choice", "prompt": "不完整选择题二", "reference_answer": "A", "score": 10},
            ],
        },
        "validation": {"issues": ["选择题缺少完整的 A、B、C、D 选项"]},
        "reflection_count": 0,
        "steps": [],
    }

    reflected = workflows.reflect_once(state)
    prompts = [item["prompt"] for item in reflected["draft"]["questions"]]

    assert len(set(prompts)) == 2
    assert all(workflows._has_complete_choice_options(prompt) for prompt in prompts)


def test_assignment_reflection_repairs_knowledge_point_mapping():
    state = {
        "kind": "assignment.draft",
        "input_data": {
            "question_count": 2,
            "question_kinds": ["short_answer"],
            "knowledge_point_ids": [1, 2],
        },
        "tool_results": {"course_context": {"citations": []}},
        "draft": {
            "questions": [
                {
                    "kind": "short_answer", "prompt": "问题一", "reference_answer": "答案一",
                    "score": 10, "knowledge_point_ids": [],
                },
                {
                    "kind": "short_answer", "prompt": "问题二", "reference_answer": "答案二",
                    "score": 10, "knowledge_point_ids": [999, "invalid"],
                },
            ],
        },
        "validation": {"issues": ["知识点映射无效"]},
        "reflection_count": 0,
        "steps": [],
    }

    reflected = workflows.reflect_once(state)

    assert [item["knowledge_point_ids"] for item in reflected["draft"]["questions"]] == [
        [1], [2],
    ]


def test_assignment_request_requires_enough_questions_for_selected_kinds():
    with pytest.raises(ValueError):
        AssignmentDraftRequest(
            question_count=1,
            question_kinds=["short_answer", "programming"],
            idempotency_key="mixed-kind-test",
        )


def test_grading_validation_rejects_an_excerpt_not_found_in_student_answer():
    state = {
        "kind": "grading.single",
        "tool_results": {
            "answers": [{
                "answer_id": 7,
                "question_id": 3,
                "question_kind": "short_answer",
                "question": "什么是进程？",
                "student_answer": "运行中的程序",
                "reference_answer": "进程是程序的一次执行过程",
                "max_score": 10,
            }],
            "missing_question_ids": [],
        },
        "draft": {
            "items": [{
                "answer_id": 7,
                "score": 8,
                "max_score": 10,
                "rubric": ["说明动态执行特征"],
                "comment": "基本正确",
                "evidence_excerpt": "程序的一次执行过程",
                "confidence": 85,
            }],
            "total_score": 8,
            "overall_comment": "基本掌握",
            "confidence": 85,
            "needs_review": True,
        },
    }

    validation = workflows._validate(state)

    assert validation.valid is False
    assert any("无法在学生原答案中定位" in issue for issue in validation.issues)


def test_grading_reflection_does_not_turn_normal_confirmation_into_priority_review():
    state = {
        "kind": "grading.single",
        "prompt": "按评分点给分",
        "tool_results": {
            "answers": [{
                "answer_id": 1,
                "question_id": 1,
                "question_kind": "short_answer",
                "student_answer": "运行中的程序",
                "reference_answer": "进程是程序的一次执行过程",
                "max_score": 10,
            }],
            "missing_question_ids": [],
        },
        "draft": {
            "items": [{
                "answer_id": 1,
                "score": 8,
                "max_score": 10,
                "rubric": ["说明动态执行特征"],
                "comment": "基本正确",
                "evidence_excerpt": "运行中的程序",
                "confidence": 85,
            }],
            "total_score": 8,
            "overall_comment": "基本掌握",
            "confidence": 85,
            "needs_review": False,
            "review_reason": None,
        },
        "validation": {"issues": []},
        "reflection_count": 0,
        "token_usage": {"prompt": 0, "completion": 0, "total": 0},
        "steps": [],
    }

    reflected = workflows.reflect_once(state)

    assert reflected["validation"]["issues"] == []
    assert reflected["draft"]["needs_review"] is False
    assert reflected["draft"]["review_reason"] is None


def test_assignment_analysis_fallback_covers_every_question_without_recalculating_scores():
    state = {
        "kind": "assignment.summary",
        "tool_results": {
            "assignment_stats": {
                "graded_count": 1,
                "total_score": 50,
                "average_score": 10,
                "questions": [
                    {"question_id": 11, "submission_count": 1, "max_score": 10,
                     "average_score": 10, "score_rate": 100, "error_types": {}},
                    {"question_id": 12, "submission_count": 1, "max_score": 10,
                     "average_score": 0, "score_rate": 0, "error_types": {"未作答": 1}},
                ],
            },
            "question_answers": [
                {"question_id": 11, "answer_samples": []},
                {"question_id": 12, "answer_samples": []},
            ],
        },
    }

    draft = workflows._fallback_assignment_analysis(state).model_dump()
    state["draft"] = draft
    validation = workflows._validate(state)

    assert validation.valid is True
    assert [item["question_id"] for item in draft["question_summaries"]] == [11, 12]
    assert "10 / 50" in draft["overall_summary"]


def test_assignment_analysis_rejects_unsupported_learning_state_inference():
    state = {
        "kind": "assignment.summary",
        "tool_results": {
            "assignment_stats": {"graded_count": 1},
            "question_answers": [{"question_id": 11}],
        },
        "draft": {
            "overall_summary": "仅有一份已确认作答。",
            "question_summaries": [{
                "question_id": 11,
                "summary": "学生学习态度不端正。",
                "strengths": [],
                "common_issues": [],
                "teaching_suggestion": "请根据答案补充缺失的得分点。",
                "confidence": 20,
            }],
            "confidence": 20,
        },
    }

    validation = workflows._validate(state)

    assert validation.valid is False
    assert any("学习状态推断" in issue for issue in validation.issues)
