from __future__ import annotations

from types import SimpleNamespace

import openai
from pydantic import BaseModel

from app.ai.contracts import CourseMapDraft
from app.integrations import ai_provider
from app.integrations.ai_provider import _json_payload


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
