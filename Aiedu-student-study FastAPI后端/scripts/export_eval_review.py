from __future__ import annotations

import argparse
from pathlib import Path

from app.evaluation.runner import _chunk_maps, load_dataset
from app.evaluation.schemas import GradingEvalDataset, RAGEvalDataset, RoutingEvalDataset


def _safe(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a human-review checklist for eval candidates")
    parser.add_argument("--dataset-version", default="v1")
    parser.add_argument("--offering-id", type=int, default=2)
    parser.add_argument("--output", type=Path, default=Path("evals/results/review_v1.md"))
    args = parser.parse_args()
    root = Path(__file__).parents[1]
    source = root / "evals" / args.dataset_version
    rag = load_dataset(source / "rag.json", RAGEvalDataset, official=False, suite="rag")
    grading = load_dataset(
        source / "grading.json", GradingEvalDataset, official=False, suite="grading",
    )
    routing = load_dataset(
        source / "routing.json", RoutingEvalDataset, official=False, suite="routing",
    )
    _, chunks = _chunk_maps(args.offering_id)
    lines = [
        f"# AIedu {args.dataset_version} 评测候选人工审核清单", "",
        "> 本文档只用于审核。请核对源 JSON 后逐条修改 approved；不要仅根据自动建议批量确认。", "",
        "## RAG（40 条）", "",
    ]
    for case in rag.cases:
        lines.extend([
            f"### [ ] {case.id} · {case.category}", "",
            f"- 问题：{case.query}",
            f"- 可回答：{case.answerable}；端到端抽样：{case.end_to_end}",
        ])
        if not case.relevant_chunks:
            lines.append("- 建议标签：课程资料不可回答；请确认教材和大纲确实不包含该主题。")
        for reference in case.relevant_chunks:
            key = f"{reference.resource_title}::{reference.content_hash}"
            chunk = chunks.get(key)
            lines.extend([
                f"- 相关资料：{reference.resource_title}，relevance={reference.relevance}，hash={reference.content_hash}",
                f"- 原文：{_safe((chunk or {}).get('text', '[切片不存在]'))[:700]}",
            ])
        lines.append("")

    lines.extend(["## 智能批阅（10 份提交 / 30 条答案）", ""])
    for submission in grading.submissions:
        lines.extend([f"### [ ] {submission.id}", ""])
        for answer in submission.answers:
            lines.extend([
                f"- `{answer.id}` / {answer.kind} / 满分 {answer.max_score}",
                f"  - 题目：{_safe(answer.prompt)}",
                f"  - 学生答案：{_safe(answer.student_answer) or '[未作答]'}",
                f"  - 参考答案：{_safe(answer.reference_answer)}",
                f"  - Rubric：{'；'.join(_safe(item) for item in answer.rubric)}",
                f"  - 建议金标准：{answer.gold_score}，允许区间 [{answer.accepted_min}, {answer.accepted_max}]，应复核={answer.should_review}",
            ])
        lines.append("")

    lines.extend(["## 结构化意图路由（40 条）", ""])
    for case in routing.cases:
        expected = case.expected
        context = case.conversation_summary or "；".join(
            f"{item.get('role')}:{_safe(item.get('content', ''))}" for item in case.recent_messages
        )
        lines.extend([
            f"- [ ] `{case.id}` {case.question}",
            f"  - 类别：{case.category}；上下文：{context or '[无]'}",
            f"  - intent={expected.intent}；delegate={expected.delegate_student_learning_assistant}；"
            f"course={expected.search_course_materials}；web={expected.search_web}；identity={expected.identity_request}",
        ])

    lines.extend([
        "", "## 完成条件", "",
        "- [ ] 40 条 RAG 均核对问题、可回答性、切片和相关性等级。",
        "- [ ] 30 条批阅答案均核对 Rubric、分数区间和复核标签。",
        "- [ ] 40 条路由均核对意图与工具组合。",
        "- [ ] 源 JSON 中对应样本逐条设置 approved=true。",
        "- [ ] 正式命令不再报告未审核样本。",
    ])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
