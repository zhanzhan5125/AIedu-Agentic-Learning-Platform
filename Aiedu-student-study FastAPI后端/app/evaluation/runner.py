from __future__ import annotations

import json
import platform
import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.ai import tutor, workflows
from app.ai.contracts import GradingSuggestion
from app.core.config import get_settings
from app.db import SessionLocal
from app.evaluation.metrics import (
    average_metrics, binary_metrics, issue_counts, multiclass_metrics,
    paired_bootstrap_ci, percentile, retrieval_case_metrics,
)
from app.evaluation.schemas import (
    GradingEvalDataset, RAGEvalDataset, RoutingEvalDataset, assert_official_dataset,
)
from app.integrations.ai_provider import structured_completion
from app.integrations.rag import RetrievalMode, retrieve_course, retrieve_course_variants
from app.models import CourseResource, ResourceChunk


class EvalRAGAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    cited_keys: list[str] = Field(default_factory=list, max_length=6)
    abstained: bool = False


class PairwiseRAGJudge(BaseModel):
    winner: str = Field(pattern=r"^(A|B|tie)$")
    answer_a_correctness: int = Field(ge=0, le=4)
    answer_b_correctness: int = Field(ge=0, le=4)
    answer_a_groundedness: int = Field(ge=0, le=4)
    answer_b_groundedness: int = Field(ge=0, le=4)
    reason: str = Field(min_length=1, max_length=1000)


def load_dataset(path: Path, schema: type[BaseModel], *, official: bool, suite: str):
    payload = json.loads(path.read_text(encoding="utf-8"))
    dataset = schema.model_validate(payload)
    if official:
        assert_official_dataset(dataset, suite)
    return dataset


def environment_metadata(dataset_version: str, seed: int, repeat: int) -> dict[str, Any]:
    settings = get_settings()
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
        ).stdout.strip()
    except Exception:
        commit = "unknown"
    return {
        "git_commit": commit,
        "dataset_version": dataset_version,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "llm_model": settings.llm_model,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "reranker_model": settings.reranker_model,
        "seed": seed,
        "repeat": repeat,
    }


def _chunk_maps(offering_id: int) -> tuple[dict[int, str], dict[str, dict[str, Any]]]:
    by_id: dict[int, str] = {}
    by_key: dict[str, dict[str, Any]] = {}
    with SessionLocal() as db:
        rows = db.execute(
            select(ResourceChunk, CourseResource.title)
            .join(CourseResource, CourseResource.id == ResourceChunk.resource_id)
            .where(ResourceChunk.offering_id == offering_id, CourseResource.deleted_at.is_(None))
        ).all()
    for chunk, title in rows:
        key = f"{title}::{chunk.content_hash}"
        by_id[chunk.id] = key
        by_key[key] = {
            "chunk_id": chunk.id, "resource_title": title,
            "content_hash": chunk.content_hash, "text": chunk.text,
            "page_number": chunk.page_number, "slide_number": chunk.slide_number,
        }
    return by_id, by_key


def _ranked_keys(results: list[dict], by_id: dict[int, str]) -> list[str]:
    values = []
    for item in results:
        key = by_id.get(item.get("chunk_id"))
        if key and key not in values:
            values.append(key)
    return values


def _rag_answer(question: str, evidence: list[dict]) -> tuple[dict, dict]:
    value, metadata = structured_completion(
        EvalRAGAnswer,
        system_prompt=(
            "你是课程 RAG 评测回答器。只能依据 evidence 回答；每个引用必须原样使用 evidence_key。"
            "如果证据不能回答问题，应明确说明资料未包含并设置 abstained=true，不能用常识补全。"
        ),
        user_prompt=json.dumps({"question": question, "evidence": evidence}, ensure_ascii=False),
        max_tokens=1800, max_retries=0,
    )
    return value.model_dump(), metadata


def _judge_rag_pair(question: str, gold: list[dict], answer_a: dict, answer_b: dict):
    value, metadata = structured_completion(
        PairwiseRAGJudge,
        system_prompt=(
            "你是盲化 RAG 回答评审。根据 gold_evidence 判断两份回答的事实正确性和可溯源性。"
            "不可回答问题中，明确拒答优于编造。不得根据回答顺序或写作风格偏好作判断。"
        ),
        user_prompt=json.dumps({
            "question": question, "gold_evidence": gold,
            "answer_a": answer_a, "answer_b": answer_b,
        }, ensure_ascii=False),
        max_tokens=1200, max_retries=0,
    )
    return value.model_dump(), metadata


def run_rag_suite(
    dataset: RAGEvalDataset, *, offering_id: int, seed: int,
    require_reranker: bool = True, run_end_to_end: bool = True,
) -> dict[str, Any]:
    by_id, by_key = _chunk_maps(offering_id)
    missing = []
    for case in dataset.cases:
        for item in case.relevant_chunks:
            key = f"{item.resource_title}::{item.content_hash}"
            if key not in by_key:
                missing.append(f"{case.id}:{key}")
    if missing:
        raise ValueError("评测集引用的切片不存在：" + ", ".join(missing[:10]))

    # Warm up the local model once. The formal rerank suite must never silently degrade.
    warmup_case = next((item for item in dataset.cases if item.answerable), None)
    if warmup_case and require_reranker:
        retrieve_course(
            offering_id, warmup_case.query, mode="hybrid_rerank", limit=6,
            require_reranker=True,
        )

    modes: list[RetrievalMode] = ["bm25", "dense", "hybrid", "hybrid_rerank"]
    mode_rows: dict[str, list[dict]] = defaultdict(list)
    case_rows: list[dict] = []
    for case in dataset.cases:
        relevance = {
            f"{item.resource_title}::{item.content_hash}": item.relevance
            for item in case.relevant_chunks
        }
        row = {
            "id": case.id, "category": case.category, "query": case.query,
            "answerable": case.answerable, "modes": {},
        }
        variants = retrieve_course_variants(
            offering_id, case.query, limit=10, require_reranker=require_reranker,
        )
        for mode in modes:
            retrieval = variants[mode]
            keys = _ranked_keys(retrieval.results, by_id)
            metrics = retrieval_case_metrics(keys, relevance) if case.answerable else {}
            value = {
                "ranked_keys": keys, "metrics": metrics,
                "timings_ms": retrieval.timings_ms,
                "diagnostics": retrieval.diagnostics,
            }
            row["modes"][mode] = value
            if case.answerable:
                mode_rows[mode].append(metrics)
        case_rows.append(row)

    summaries = {}
    for mode in modes:
        latencies = [row["modes"][mode]["timings_ms"]["total"] for row in case_rows]
        summaries[mode] = {
            **average_metrics(mode_rows[mode]),
            "latency_p50_ms": percentile(latencies, 0.5),
            "latency_p95_ms": percentile(latencies, 0.95),
        }
    answerable_rows = [row for row in case_rows if row["answerable"]]
    comparison = {}
    for metric in ("recall_at_5", "ndcg_at_5"):
        comparison[metric] = paired_bootstrap_ci(
            [row["modes"]["hybrid"]["metrics"][metric] for row in answerable_rows],
            [row["modes"]["hybrid_rerank"]["metrics"][metric] for row in answerable_rows],
            seed=seed,
        )
    hybrid_rerank_latency = [row["modes"]["hybrid_rerank"]["timings_ms"]["rerank"]
                             for row in case_rows]
    decision = {
        "recommend_reranker": (
            comparison["ndcg_at_5"]["delta"] >= 0.03 and
            comparison["recall_at_5"]["delta"] >= -0.01 and
            percentile(hybrid_rerank_latency, 0.95) <= 500
        ),
        "criteria": {
            "minimum_ndcg_at_5_delta": 0.03,
            "minimum_recall_at_5_delta": -0.01,
            "maximum_rerank_p95_ms": 500,
        },
        "rerank_p95_ms": percentile(hybrid_rerank_latency, 0.95),
    }

    end_to_end = []
    if run_end_to_end:
        rng = random.Random(seed)
        for case in [item for item in dataset.cases if item.end_to_end]:
            case_row = next(item for item in case_rows if item["id"] == case.id)
            answers = {}
            usages = {}
            variants = retrieve_course_variants(
                offering_id, case.query, limit=6, require_reranker=require_reranker,
            )
            for mode in ("hybrid", "hybrid_rerank"):
                retrieval = variants[mode]
                evidence = [{
                    "evidence_key": by_id.get(item.get("chunk_id"), "unknown"),
                    "text": item.get("text", ""),
                } for item in retrieval.results]
                answers[mode], metadata = _rag_answer(case.query, evidence)
                usages[mode] = metadata.get("token_usage") or {}
            order = ["hybrid", "hybrid_rerank"]
            rng.shuffle(order)
            gold = [by_key[f"{item.resource_title}::{item.content_hash}"]
                    for item in case.relevant_chunks]
            judge, judge_metadata = _judge_rag_pair(
                case.query, gold, answers[order[0]], answers[order[1]],
            )
            mapped_winner = "tie" if judge["winner"] == "tie" else order[0 if judge["winner"] == "A" else 1]
            end_to_end.append({
                "id": case.id, "question": case.query, "answerable": case.answerable,
                "answers": answers, "blind_order": order, "judge": judge,
                "winner": mapped_winner, "token_usage": usages,
                "judge_token_usage": judge_metadata.get("token_usage") or {},
                "human_audit_required": True,
            })

    wins = {mode: sum(item["winner"] == mode for item in end_to_end)
            for mode in ("hybrid", "hybrid_rerank", "tie")}
    return {
        "suite": "rag", "summary": summaries, "rerank_comparison": comparison,
        "reranker_decision": decision, "cases": case_rows,
        "end_to_end": {"summary": wins, "cases": end_to_end,
                       "status": "pending_human_audit" if end_to_end else "not_run"},
    }


def _grading_state(case) -> dict[str, Any]:
    answers = []
    for index, item in enumerate(case.answers, 1):
        answers.append({
            "answer_id": index, "question_id": index, "question_kind": item.kind,
            "prompt": item.prompt, "reference_answer": item.reference_answer,
            "rubric": item.rubric, "max_score": item.max_score,
            "student_answer": item.student_answer,
        })
    return {
        "kind": "grading.single", "prompt": case.teacher_rules,
        "tool_results": {"answers": answers, "missing_question_ids": []},
        "steps": [], "reflection_count": 0,
        "token_usage": {"prompt": 0, "completion": 0, "total": 0},
    }


def _grading_metrics(dataset: GradingEvalDataset, rows: list[dict], mode: str) -> dict[str, Any]:
    absolute_errors = []
    in_ranges = []
    boundary_ok = []
    covered = []
    evidence_ok = []
    review_expected = []
    review_actual = []
    total_consistent = []
    validations = []
    for case, row in zip(dataset.submissions, rows, strict=True):
        result = row[mode]["result"]
        items = {int(item["answer_id"]): item for item in result.get("items", [])}
        for index, gold in enumerate(case.answers, 1):
            item = items.get(index)
            covered.append(item is not None)
            if not item:
                absolute_errors.append(1.0)
                in_ranges.append(False)
                boundary_ok.append(False)
                evidence_ok.append(False)
                continue
            score = int(item.get("score", 0))
            absolute_errors.append(abs(score - gold.gold_score) / gold.max_score)
            in_ranges.append(gold.accepted_min <= score <= gold.accepted_max)
            boundary_ok.append(0 <= score <= gold.max_score and
                               int(item.get("max_score", -1)) == gold.max_score)
            excerpt = "".join((item.get("evidence_excerpt") or "").split())
            original = "".join(gold.student_answer.split())
            evidence_ok.append(bool(excerpt) and (
                excerpt in original if original else excerpt == "未作答"
            ))
        review_expected.append(any(item.should_review for item in case.answers))
        review_actual.append(bool(result.get("needs_review")))
        total_consistent.append(int(result.get("total_score", -1)) ==
                                sum(int(item.get("score", 0)) for item in result.get("items", [])))
        validations.append(row[mode]["validation"].get("issues", []))
    return {
        "normalized_mae": round(mean(absolute_errors), 4),
        "within_accepted_range": round(sum(in_ranges) / max(1, len(in_ranges)), 4),
        "boundary_valid_rate": round(sum(boundary_ok) / max(1, len(boundary_ok)), 4),
        "answer_coverage_rate": round(sum(covered) / max(1, len(covered)), 4),
        "evidence_support_rate": round(sum(evidence_ok) / max(1, len(evidence_ok)), 4),
        "total_consistency_rate": round(sum(total_consistent) / max(1, len(total_consistent)), 4),
        "human_review": binary_metrics(review_expected, review_actual),
        "validation_pass_rate": round(sum(not issues for issues in validations) /
                                      max(1, len(validations)), 4),
        "validation_issue_counts": issue_counts(validations),
    }


def run_grading_suite(
    dataset: GradingEvalDataset, *, input_cost_per_million: float = 0,
    output_cost_per_million: float = 0,
) -> dict[str, Any]:
    rows = []
    for case in dataset.submissions:
        state = _grading_state(case)
        total_started = perf_counter()
        started = perf_counter()
        raw, metadata = workflows._model_grading(state)
        raw_latency = round((perf_counter() - started) * 1000, 3)
        raw_state = {**state, "draft": raw}
        raw_validation = workflows._validate(raw_state).model_dump()
        validated_state = {**raw_state, "validation": raw_validation,
                           "token_usage": metadata.get("token_usage") or {}}
        reflection_started = perf_counter()
        reflected_state = workflows.reflect_once(validated_state)
        reflection_latency = round((perf_counter() - reflection_started) * 1000, 3)
        reflected = reflected_state["draft"]
        reflected_validation = reflected_state["validation"]
        rows.append({
            "id": case.id,
            "raw": {"result": raw, "validation": raw_validation},
            "validate": {"result": raw, "validation": raw_validation},
            "reflect": {"result": reflected, "validation": reflected_validation},
            "raw_latency_ms": raw_latency,
            "reflection_latency_ms": reflection_latency,
            "total_latency_ms": round((perf_counter() - total_started) * 1000, 3),
            "token_usage": reflected_state.get("token_usage") or metadata.get("token_usage") or {},
            "reflection_triggered": bool(raw_validation.get("issues")),
            "reflection_repaired": bool(raw_validation.get("issues")) and not reflected_validation.get("issues"),
            "reflection_regressed": not raw_validation.get("issues") and bool(reflected_validation.get("issues")),
        })
    summaries = {mode: _grading_metrics(dataset, rows, mode)
                 for mode in ("raw", "validate", "reflect")}
    triggered = [item for item in rows if item["reflection_triggered"]]
    usage = [item["token_usage"] for item in rows]
    total_cost = sum(
        (float(item.get("prompt") or 0) * input_cost_per_million +
         float(item.get("completion") or 0) * output_cost_per_million) / 1_000_000
        for item in usage
    ) if input_cost_per_million or output_cost_per_million else None
    reflection = {
        "trigger_rate": round(len(triggered) / max(1, len(rows)), 4),
        "repair_success_rate": round(sum(item["reflection_repaired"] for item in triggered) /
                                     max(1, len(triggered)), 4),
        "regression_rate": round(sum(item["reflection_regressed"] for item in rows) /
                                 max(1, len(rows)), 4),
        "retain_conditional_reflection": (
            (sum(item["reflection_repaired"] for item in triggered) / max(1, len(triggered))) >= 0.30 and
            summaries["reflect"]["normalized_mae"] <= summaries["raw"]["normalized_mae"] + 0.01
        ),
    }
    raw_latencies = [item["raw_latency_ms"] for item in rows]
    reflection_latencies = [item["reflection_latency_ms"] for item in rows]
    total_latencies = [item["total_latency_ms"] for item in rows]
    return {
        "suite": "grading", "summary": summaries, "reflection": reflection,
        "performance": {
            "raw_latency_p50_ms": percentile(raw_latencies, 0.5),
            "raw_latency_p95_ms": percentile(raw_latencies, 0.95),
            "reflection_latency_p50_ms": percentile(reflection_latencies, 0.5),
            "total_latency_p50_ms": percentile(total_latencies, 0.5),
            "total_latency_p95_ms": percentile(total_latencies, 0.95),
            "prompt_tokens": sum(int(item.get("prompt") or 0) for item in usage),
            "completion_tokens": sum(int(item.get("completion") or 0) for item in usage),
            "estimated_cost_usd": round(total_cost, 6) if total_cost is not None else None,
            "average_estimated_cost_usd": round(total_cost / len(rows), 6)
            if total_cost is not None and rows else None,
        },
        "cases": rows,
    }


def _routing_dict(value) -> dict[str, Any]:
    return value.model_dump() if hasattr(value, "model_dump") else dict(value)


def _routing_signature(value: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(value.get(key) for key in (
        "intent", "delegate_student_learning_assistant", "search_course_materials",
        "search_web", "identity_request",
    ))


def _routing_summary(dataset: RoutingEvalDataset, rows: list[dict], mode: str) -> dict[str, Any]:
    expected_intents = [item.expected.intent for item in dataset.cases]
    actual = [row[mode]["decision"] for row in rows]
    actual_intents = [item["intent"] for item in actual]
    expected_delegate = [item.expected.delegate_student_learning_assistant for item in dataset.cases]
    actual_delegate = [bool(item["delegate_student_learning_assistant"]) for item in actual]
    exact_tools = []
    for case, decision in zip(dataset.cases, actual, strict=True):
        exact_tools.append(all([
            case.expected.delegate_student_learning_assistant == decision["delegate_student_learning_assistant"],
            case.expected.search_course_materials == decision["search_course_materials"],
            case.expected.search_web == decision["search_web"],
            case.expected.identity_request == decision["identity_request"],
        ]))
    return {
        **multiclass_metrics(expected_intents, actual_intents),
        "delegation": binary_metrics(expected_delegate, actual_delegate),
        "tool_exact_match": round(sum(exact_tools) / max(1, len(exact_tools)), 4),
        "unnecessary_delegation_rate": round(
            sum(not expected and found for expected, found in zip(expected_delegate, actual_delegate, strict=True)) /
            max(1, sum(not value for value in expected_delegate)), 4,
        ),
        "missed_delegation_rate": round(
            sum(expected and not found for expected, found in zip(expected_delegate, actual_delegate, strict=True)) /
            max(1, sum(expected_delegate)), 4,
        ),
    }


def run_routing_suite(dataset: RoutingEvalDataset, *, repeat: int = 1) -> dict[str, Any]:
    rows = []
    for case in dataset.cases:
        memory = {
            "summary": case.conversation_summary,
            "recent_messages": case.recent_messages,
        }
        baseline = tutor._fallback_routing(case.question, memory)
        runs = max(repeat, 2 if case.repeat else repeat)
        model_values = []
        metadata_values = []
        modes = []
        latencies = []
        for _ in range(runs):
            started = perf_counter()
            decision, metadata, route_mode = tutor._route_with_model(case.question, memory)
            latencies.append(round((perf_counter() - started) * 1000, 3))
            model_values.append(_routing_dict(decision))
            metadata_values.append(metadata)
            modes.append(route_mode)
        rows.append({
            "id": case.id, "category": case.category, "question": case.question,
            "expected": case.expected.model_dump(),
            "rules": {"decision": _routing_dict(baseline)},
            "model": {"decision": model_values[0], "route_mode": modes[0]},
            "model_runs": model_values, "route_modes": modes,
            "consistent": all(
                _routing_signature(item) == _routing_signature(model_values[0])
                for item in model_values
            ),
            "latency_ms": latencies,
            "token_usage": [item.get("token_usage") or {} for item in metadata_values],
        })
    model_modes = [mode for row in rows for mode in row["route_modes"]]
    latencies = [value for row in rows for value in row["latency_ms"]]
    repeat_rows = [row for row in rows if len(row["model_runs"]) > 1]
    usages = [value for row in rows for value in row["token_usage"]]
    return {
        "suite": "routing",
        "summary": {
            "rules": _routing_summary(dataset, rows, "rules"),
            "model": _routing_summary(dataset, rows, "model"),
        },
        "performance": {
            "structured_output_failure_rate": round(sum(mode != "model" for mode in model_modes) /
                                                    max(1, len(model_modes)), 4),
            "fallback_rate": round(sum(mode == "deterministic-fallback" for mode in model_modes) /
                                   max(1, len(model_modes)), 4),
            "repeat_consistency_rate": round(sum(row["consistent"] for row in repeat_rows) /
                                             max(1, len(repeat_rows)), 4),
            "latency_p50_ms": percentile(latencies, 0.5),
            "latency_p95_ms": percentile(latencies, 0.95),
            "prompt_tokens": sum(int(item.get("prompt") or 0) for item in usages),
            "completion_tokens": sum(int(item.get("completion") or 0) for item in usages),
        },
        "cases": rows,
    }
