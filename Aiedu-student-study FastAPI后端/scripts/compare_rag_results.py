from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean


def _suite(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return next(item for item in payload["suites"] if item["suite"] == "rag")


def _category_metrics(suite: dict, mode: str) -> dict[str, dict[str, float]]:
    values: dict[str, list[dict[str, float]]] = defaultdict(list)
    for case in suite["cases"]:
        if case["answerable"]:
            values[case["category"]].append(case["modes"][mode]["metrics"])
    return {
        category: {
            metric: round(mean(row[metric] for row in rows), 4)
            for metric in ("recall_at_5", "ndcg_at_5", "hit_at_1")
        }
        for category, rows in sorted(values.items())
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two saved RAG evaluation results")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    baseline = _suite(args.baseline)
    candidate = _suite(args.candidate)
    output = {"overall": {}, "categories": {}}
    for mode in ("bm25", "dense", "hybrid", "hybrid_rerank"):
        output["overall"][mode] = {
            metric: {
                "baseline": baseline["summary"][mode][metric],
                "candidate": candidate["summary"][mode][metric],
                "delta": round(
                    candidate["summary"][mode][metric] - baseline["summary"][mode][metric], 4
                ),
            }
            for metric in ("recall_at_5", "ndcg_at_5", "hit_at_1")
        }
        output["categories"][mode] = {
            "baseline": _category_metrics(baseline, mode),
            "candidate": _category_metrics(candidate, mode),
        }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
