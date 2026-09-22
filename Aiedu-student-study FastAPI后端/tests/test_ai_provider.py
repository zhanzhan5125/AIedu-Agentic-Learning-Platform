from __future__ import annotations


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
