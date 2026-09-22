from __future__ import annotations

import json
import re
from time import perf_counter
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


def _json_payload(value: str) -> dict:
    cleaned = value.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("模型未返回 JSON 对象")
    return json.loads(cleaned[start:end + 1])


def structured_completion(
    schema: type[StructuredModel], *, system_prompt: str, user_prompt: str,
    max_tokens: int = 3000, timeout_seconds: float = 60,
) -> tuple[StructuredModel, dict]:
    """Call an OpenAI-compatible model and validate one bounded repair attempt."""
    settings = get_settings()
    if not settings.enable_llm or not settings.ai_api_key:
        raise RuntimeError("真实模型未启用")

    from openai import OpenAI

    client = OpenAI(
        api_key=settings.ai_api_key,
        base_url=settings.ai_base_url,
        timeout=timeout_seconds,
        max_retries=1,
    )
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    messages = [
        {"role": "system", "content": (
            f"{system_prompt}\n只返回符合以下 JSON Schema 的 JSON 对象，不要使用 Markdown：\n{schema_json}"
        )},
        {"role": "user", "content": user_prompt},
    ]
    started = perf_counter()
    last_error: Exception | None = None
    total_usage = {"prompt": 0, "completion": 0, "total": 0}
    for attempt in range(2):
        kwargs = {
            "model": settings.llm_model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        try:
            response = client.chat.completions.create(
                **kwargs, response_format={"type": "json_object"}
            )
        except Exception as exc:
            # Some OpenAI-compatible gateways do not implement response_format.
            if attempt == 0 and "response_format" in str(exc):
                response = client.chat.completions.create(**kwargs)
            else:
                raise
        content = response.choices[0].message.content if response.choices else ""
        usage = response.usage
        if usage:
            total_usage["prompt"] += getattr(usage, "prompt_tokens", 0) or 0
            total_usage["completion"] += getattr(usage, "completion_tokens", 0) or 0
            total_usage["total"] += getattr(usage, "total_tokens", 0) or 0
        try:
            value = schema.model_validate(_json_payload(content or ""))
            return value, {
                "model": getattr(response, "model", None) or settings.llm_model,
                "latency_ms": round((perf_counter() - started) * 1000),
                "token_usage": total_usage,
                "repair_attempted": attempt == 1,
            }
        except (ValueError, json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            if attempt == 0:
                messages.extend([
                    {"role": "assistant", "content": content or ""},
                    {"role": "user", "content": (
                        f"上一次输出未通过结构校验：{str(exc)[:1000]}。"
                        "请修复并仅返回完整 JSON 对象。"
                    )},
                ])
    raise RuntimeError(f"模型结构化输出校验失败：{last_error}")


def provider_status() -> dict:
    settings = get_settings()
    return {
        "configured": bool(settings.ai_api_key),
        "enabled": settings.enable_llm,
        "base_url": settings.ai_base_url,
        "chat_model": settings.llm_model,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
    }


def chat_completion(prompt: str) -> dict:
    settings = get_settings()
    if not settings.ai_api_key:
        raise RuntimeError("尚未配置 AIEDU_AI_API_KEY")

    from openai import OpenAI

    started = perf_counter()
    response = OpenAI(
        api_key=settings.ai_api_key,
        base_url=settings.ai_base_url,
        timeout=60,
        max_retries=1,
    ).chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": "你是 AIedu 的连通性测试助手，请简短回答。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        max_tokens=128,
    )
    content = response.choices[0].message.content if response.choices else ""
    usage = response.usage
    return {
        "model": getattr(response, "model", None) or settings.llm_model,
        "content": content or "",
        "latency_ms": round((perf_counter() - started) * 1000),
        "token_usage": {
            "prompt": getattr(usage, "prompt_tokens", None),
            "completion": getattr(usage, "completion_tokens", None),
            "total": getattr(usage, "total_tokens", None),
        } if usage else None,
    }


def embedding_probe(text: str) -> dict:
    from app.integrations.rag import embed_texts

    settings = get_settings()
    started = perf_counter()
    vector = embed_texts([text])[0]
    return {
        "model": settings.embedding_model,
        "dimensions": len(vector),
        "latency_ms": round((perf_counter() - started) * 1000),
        "vector_norm": round(sum(value * value for value in vector) ** 0.5, 6),
    }
