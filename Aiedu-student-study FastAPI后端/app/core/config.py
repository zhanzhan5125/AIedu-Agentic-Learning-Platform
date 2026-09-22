from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIEDU_", env_file=".env", extra="ignore", case_sensitive=False
    )

    env: Literal["development", "test", "production"] = "development"
    app_name: str = "AIedu API"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./aiedu-dev.db"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    jwt_secret: str = "development-only-change-this-secret"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    # Docker/.env uses a convenient comma-separated value. NoDecode prevents
    # pydantic-settings from requiring JSON before our validator can split it.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:8080"]
    )
    rocketmq_endpoint: str = "localhost:8081"
    rocketmq_topic: str = "aiedu-ai-jobs"
    rocketmq_log_dir: str = "./logs/rocketmq_python"
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    llm_model: str = "qwen-plus"
    enable_mq: bool = False
    enable_llm: bool = False
    upload_dir: str = "./uploads"
    max_upload_bytes: int = 10 * 1024 * 1024
    object_storage_backend: Literal["local", "minio"] = "local"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "aiedu"
    minio_secret_key: str = "aiedu-development"
    minio_bucket: str = "aiedu-resources"
    minio_secure: bool = False
    # Versioned to avoid mixing the previous 64-dimension development vectors
    # with real text-embedding-3-large vectors.
    qdrant_collection: str = "aiedu_course_resources_v2"
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072
    embedding_batch_size: int = 64
    rag_chunk_size_chars: int = 1200
    rag_chunk_overlap_chars: int = 200
    rag_chunk_target_tokens: int = 550
    rag_chunk_max_tokens: int = 800
    rag_chunk_overlap_tokens: int = 80
    enable_local_reranker: bool = True
    reranker_model: str = "BAAI/bge-reranker-base"
    tavily_api_key: str = ""
    tavily_base_url: str = "https://api.tavily.com/search"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("jwt_secret")
    @classmethod
    def validate_secret(cls, value: str, info):
        if info.data.get("env") == "production" and len(value) < 32:
            raise ValueError("AIEDU_JWT_SECRET must contain at least 32 characters")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
