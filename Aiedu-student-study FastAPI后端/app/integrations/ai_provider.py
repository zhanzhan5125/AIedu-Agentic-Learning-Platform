from __future__ import annotations

import json
import re
from time import perf_counter
from typing import TypeVar

from json_repair import repair_json
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


def _json_payload(value: str) -> tuple[dict, bool]:
    cleaned = value.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0:
        raise ValueError("模型未返回 JSON 对象")
    candidate = cleaned[start:end + 1] if end >= start else cleaned[start:]
    try:
        payload = json.loads(candidate)
        repaired = False
    except json.JSONDecodeError:
        payload = repair_json(candidate, return_objects=True)
        repaired = True
    if not isinstance(payload, dict):
        raise ValueError("模型未返回 JSON 对象")
    return payload, repaired


def structured_completion(
    schema: type[StructuredModel], *, system_prompt: str, user_prompt: str,
    max_tokens: int = 3000, timeout_seconds: float = 60, max_retries: int = 1,
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
        max_retries=max_retries,
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
    last_diagnostic = "finish_reason=unknown, response_chars=0"
    total_usage = {"prompt": 0, "completion": 0, "total": 0}
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": schema.__name__,
            "strict": True,
            "schema": schema.model_json_schema(),
        },
    }
    format_mode = "json_schema"
    for attempt in range(2):
        kwargs = {
            "model": settings.llm_model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        try:
            response = client.chat.completions.create(**kwargs, response_format=response_format)
        except Exception as exc:
            # Keep compatibility with gateways that support JSON mode but not
            # strict JSON Schema. Transport errors must still surface normally.
            error_text = str(exc).lower()
            if attempt == 0 and any(term in error_text for term in (
                "response_format", "json_schema", "json schema",
            )):
                response_format = {"type": "json_object"}
                format_mode = "json_object"
                response = client.chat.completions.create(
                    **kwargs, response_format=response_format,
                )
            else:
                raise
        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice else ""
        finish_reason = getattr(choice, "finish_reason", None) if choice else None
        last_diagnostic = f"finish_reason={finish_reason or 'unknown'}, response_chars={len(content or '')}"
        usage = response.usage
        if usage:
            total_usage["prompt"] += getattr(usage, "prompt_tokens", 0) or 0
            total_usage["completion"] += getattr(usage, "completion_tokens", 0) or 0
            total_usage["total"] += getattr(usage, "total_tokens", 0) or 0
        try:
            if finish_reason in {
                "length", "content_filter", "insufficient_system_resource", "aborted",
            }:
                raise ValueError(f"模型输出未正常完成：finish_reason={finish_reason}")
            payload, json_repair_applied = _json_payload(content or "")
            value = schema.model_validate(payload)
            return value, {
                "model": getattr(response, "model", None) or settings.llm_model,
                "latency_ms": round((perf_counter() - started) * 1000),
                "token_usage": total_usage,
                "repair_attempted": attempt == 1,
                "finish_reason": finish_reason,
                "response_chars": len(content or ""),
                "structured_output_mode": format_mode,
                "json_repair_applied": json_repair_applied,
            }
        except (ValueError, json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            if attempt == 0:
                messages.extend([
                    {"role": "assistant", "content": content or ""},
                    {"role": "user", "content": (
                        f"上一次输出未通过结构校验：{str(exc)[:1000]}。"
                        "请缩短冗余文字，修复 JSON 语法，并仅返回完整 JSON 对象。"
                    )},
                ])
    raise RuntimeError(f"模型结构化输出校验失败（{last_diagnostic}）：{last_error}")


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
