from __future__ import annotations

from typing import Any


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def _rag_report(result: dict) -> str:
    summary = result["summary"]
    rows = [[
        mode, values.get("recall_at_5"), values.get("recall_at_6"),
        values.get("mrr_at_10"), values.get("ndcg_at_5"), values.get("hit_at_1"),
        values.get("latency_p50_ms"), values.get("latency_p95_ms"),
    ] for mode, values in summary.items()]
    regressions = [case["id"] for case in result["cases"] if case["answerable"] and
                   case["modes"]["hybrid_rerank"]["metrics"]["ndcg_at_5"] <
                   case["modes"]["hybrid"]["metrics"]["ndcg_at_5"]]
    decision = result["reranker_decision"]
    reranker_device = (
        result["cases"][0]["modes"]["hybrid_rerank"]["diagnostics"].get("reranker_device")
        if result.get("cases") else "unknown"
    )
    return "\n".join([
        "## RAG 消融评测",
        "",
        _table(
            ["模式", "Recall@5", "Recall@6", "MRR@10", "nDCG@5", "Hit@1", "p50(ms)", "p95(ms)"],
            rows,
        ),
        "",
        f"- Rerank nDCG@5 差值：`{result['rerank_comparison']['ndcg_at_5']}`",
        f"- Rerank Recall@5 差值：`{result['rerank_comparison']['recall_at_5']}`",
        f"- Rerank warm p95：{decision['rerank_p95_ms']} ms",
        f"- Reranker 实际设备：`{reranker_device}`",
        f"- 是否推荐默认启用：{'是' if decision['recommend_reranker'] else '否'}",
        f"- 重排退化案例：{', '.join(regressions) if regressions else '无'}",
        f"- 端到端盲评：`{result['end_to_end']['summary']}`；状态：{result['end_to_end']['status']}",
    ])


def _grading_report(result: dict) -> str:
    rows = []
    for mode, values in result["summary"].items():
        rows.append([
            mode, values["normalized_mae"], values["within_accepted_range"],
            values["boundary_valid_rate"], values["answer_coverage_rate"],
            values["evidence_support_rate"], values["validation_pass_rate"],
        ])
    failures = [row["id"] for row in result["cases"]
                if row["reflect"]["validation"].get("issues")]
    return "\n".join([
        "## 智能批阅消融评测",
        "",
        _table(
            ["模式", "归一化 MAE", "允许区间命中", "边界合法", "题目覆盖", "证据支持", "校验通过"],
            rows,
        ),
        "",
        f"- Reflection：`{result['reflection']}`",
        f"- 性能与成本：`{result['performance']}`",
        f"- Reflection 后仍失败案例：{', '.join(failures) if failures else '无'}",
    ])


def _routing_report(result: dict) -> str:
    rows = []
    for mode, values in result["summary"].items():
        rows.append([
            mode, values["accuracy"], values["macro_f1"],
            values["delegation"]["precision"], values["delegation"]["recall"],
            values["delegation"]["f1"], values["tool_exact_match"],
        ])
    compared_keys = (
        "intent", "delegate_student_learning_assistant", "search_course_materials",
        "search_web", "identity_request",
    )
    failures = [row["id"] for row in result["cases"] if any(
        row["model"]["decision"].get(key) != row["expected"].get(key)
        for key in compared_keys
    )]
    return "\n".join([
        "## 结构化意图路由评测",
        "",
        _table(
            ["模式", "Accuracy", "Macro-F1", "委派 Precision", "委派 Recall", "委派 F1", "工具 Exact Match"],
            rows,
        ),
        "",
        f"- 稳定性与性能：`{result['performance']}`",
        f"- 模型路由失败案例：{', '.join(failures) if failures else '无'}",
    ])


def render_markdown(payload: dict[str, Any]) -> str:
    official = payload.get("official", False)
    title = "# AIedu Agent/RAG 正式评测报告" if official else "# AIedu Agent/RAG 预评测报告"
    lines = [title, ""]
    if not official:
        lines.extend([
            "> **非正式结果：数据尚未完成人工确认，不得写入简历或作为正式性能声明。**",
            "",
        ])
    metadata = payload.get("metadata", {})
    lines.extend([
        "## 运行信息", "",
        f"- Git commit：`{metadata.get('git_commit', 'unknown')}`",
        f"- 数据版本：`{metadata.get('dataset_version')}`",
        f"- LLM：`{metadata.get('llm_model')}`",
        f"- Embedding：`{metadata.get('embedding_model')}`",
        f"- Reranker：`{metadata.get('reranker_model')}`",
        f"- 运行时间：`{payload.get('generated_at')}`",
        "",
    ])
    for suite in payload.get("suites", []):
        renderer = {"rag": _rag_report, "grading": _grading_report, "routing": _routing_report}[suite["suite"]]
        lines.extend([renderer(suite), ""])
    lines.extend([
        "## 使用限制", "",
        "- 所有简历数字必须来自本报告对应的 JSON 原始结果。",
        "- RAG 端到端 Judge 结果在人工盲审完成前只能作为辅助指标。",
        "- 负向或无提升结果必须保留，不得选择性删除失败案例。",
    ])
    return "\n".join(lines).rstrip() + "\n"
