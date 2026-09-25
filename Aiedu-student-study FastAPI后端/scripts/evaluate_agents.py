from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.evaluation.report import render_markdown
from app.evaluation.runner import (
    environment_metadata, load_dataset, run_grading_suite, run_rag_suite, run_routing_suite,
)
from app.evaluation.schemas import GradingEvalDataset, RAGEvalDataset, RoutingEvalDataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Run reproducible AIedu Agent/RAG evaluations")
    parser.add_argument("--suite", choices=["rag", "grading", "routing", "all"], default="all")
    parser.add_argument("--dataset-version", default="v1")
    parser.add_argument("--offering-id", type=int, default=2)
    parser.add_argument("--output", type=Path, default=Path("evals/results"))
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--draft", action="store_true", help="Allow unapproved candidate data; report is watermarked")
    parser.add_argument("--allow-reranker-fallback", action="store_true")
    parser.add_argument("--skip-end-to-end", action="store_true")
    parser.add_argument("--max-cases", type=int, help="Draft-only smoke-test limit")
    parser.add_argument("--input-cost-per-million", type=float, default=0)
    parser.add_argument("--output-cost-per-million", type=float, default=0)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat 必须大于 0")
    if args.max_cases is not None and (args.max_cases < 1 or not args.draft):
        parser.error("--max-cases 只能与 --draft 一起使用，且必须大于 0")

    root = Path(__file__).parents[1]
    dataset_dir = root / "evals" / args.dataset_version
    suites = [args.suite] if args.suite != "all" else ["rag", "grading", "routing"]
    results = []
    schemas = {
        "rag": (RAGEvalDataset, "rag.json"),
        "grading": (GradingEvalDataset, "grading.json"),
        "routing": (RoutingEvalDataset, "routing.json"),
    }
    loaded = {}
    for suite in suites:
        schema, filename = schemas[suite]
        try:
            loaded[suite] = load_dataset(
                dataset_dir / filename, schema, official=not args.draft, suite=suite,
            )
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        if args.max_cases:
            field = "submissions" if suite == "grading" else "cases"
            loaded[suite] = loaded[suite].model_copy(update={
                field: getattr(loaded[suite], field)[:args.max_cases],
            })
    if "rag" in suites:
        results.append(run_rag_suite(
            loaded["rag"], offering_id=args.offering_id, seed=args.seed,
            require_reranker=not args.allow_reranker_fallback,
            run_end_to_end=not args.skip_end_to_end,
        ))
    if "grading" in suites:
        results.append(run_grading_suite(
            loaded["grading"],
            input_cost_per_million=args.input_cost_per_million,
            output_cost_per_million=args.output_cost_per_million,
        ))
    if "routing" in suites:
        results.append(run_routing_suite(loaded["routing"], repeat=args.repeat))

    generated = datetime.now(UTC)
    payload = {
        "official": not args.draft,
        "generated_at": generated.isoformat(),
        "metadata": environment_metadata(args.dataset_version, args.seed, args.repeat),
        "suites": results,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    stem = f"{generated.strftime('%Y%m%dT%H%M%SZ')}_{args.suite}_{args.dataset_version}"
    json_path = args.output / f"{stem}.json"
    markdown_path = args.output / f"{stem}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps({
        "official": payload["official"], "json": str(json_path),
        "markdown": str(markdown_path), "suites": suites,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
