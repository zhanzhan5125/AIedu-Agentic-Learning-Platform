from __future__ import annotations

from types import SimpleNamespace

import openai
import pytest
from pydantic import BaseModel

from app.ai.contracts import CourseMapDraft
from app.ai import workflows
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
