from __future__ import annotations

import hashlib
import os

os.environ["AIEDU_ENV"] = "test"
os.environ["AIEDU_DATABASE_URL"] = "sqlite:///./test-aiedu.db"
os.environ["AIEDU_REDIS_URL"] = "redis://127.0.0.1:6399/15"
os.environ["AIEDU_JWT_SECRET"] = "test-secret-that-is-long-enough-for-tests"
os.environ["AIEDU_ENABLE_LLM"] = "false"
os.environ["AIEDU_AI_API_KEY"] = ""
os.environ["AIEDU_ENABLE_LOCAL_RERANKER"] = "false"

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Role, User


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as db:
        db.add_all([
            User(role=Role.manager, account="admin", display_name="管理员",
                 password_hash=hash_password("password123")),
            User(role=Role.teacher, account="teacher", display_name="教师",
                 password_hash=hashlib.md5(b"password123").hexdigest(), password_migrated=False),
            User(role=Role.student, account="student", display_name="学生",
                 password_hash=hash_password("password123")),
        ])
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    with TestClient(app) as value:
        yield value


def login(client: TestClient, role: str, account: str) -> str:
    response = client.post("/api/v1/auth/login", json={
        "role": role, "account": account, "password": "password123"
    })
    assert response.status_code == 200, response.text
    return response.json()["data"]["token"]


@pytest.fixture
def auth():
    return login
