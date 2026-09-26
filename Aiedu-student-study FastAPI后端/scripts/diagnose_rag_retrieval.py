from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from app.evaluation.metrics import average_metrics, retrieval_case_metrics
from app.evaluation.runner import _chunk_maps, load_dataset
from app.evaluation.schemas import RAGEvalDataset
from app.db import SessionLocal
from app.integrations.rag import (
    _apply_source_preferences,
    _bm25_search,
    _dense_search,
    _rrf,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect per-case RAG retrieval failures")
    parser.add_argument("--dataset-version", default="v2")
    parser.add_argument("--offering-id", type=int, default=2)
    parser.add_argument("--mode", choices=["bm25", "dense", "hybrid"], default="hybrid")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    root = Path(__file__).parents[1]
    dataset = load_dataset(
        root / "evals" / args.dataset_version / "rag.json",
        RAGEvalDataset,
        official=True,
        suite="rag",
    )
    by_id, by_key = _chunk_maps(args.offering_id)
    category_rows: dict[str, list[dict[str, float]]] = defaultdict(list)
    failures: list[tuple[float, str, str, list[str], list[str]]] = []

    session = SessionLocal()
    for case in dataset.cases:
        if not case.answerable:
            continue
        relevance = {
            f"{item.resource_title}::{item.content_hash}": item.relevance
            for item in case.relevant_chunks
        }
        dense = _dense_search(args.offering_id, case.query, 20)
        lexical = _bm25_search(session, args.offering_id, case.query, 20)
        candidates = {
            "bm25": lexical,
            "dense": dense,
            "hybrid": _rrf(dense, lexical),
        }[args.mode]
        results = _apply_source_preferences(case.query, candidates)[:args.limit]
        keys = [by_id.get(item.get("chunk_id"), "unknown") for item in results]
        metrics = retrieval_case_metrics(keys, relevance)
        category_rows[case.category].append(metrics)
        if metrics["recall_at_5"] < 1:
            gold = []
            for key in relevance:
                chunk = by_key[key]
                gold.append(
                    f"{key.split('::', 1)[0]} | {chunk.get('heading_path')} | "
                    f"{chunk['text'][:80].replace(chr(10), ' ')}"
                )
            actual = [
                f"{item.get('title')} | {item.get('heading_path')} | "
                f"{str(item.get('text', ''))[:80].replace(chr(10), ' ')}"
                for item in results[:5]
            ]
            failures.append((metrics["recall_at_5"], case.id, case.query, gold, actual))

    print("category metrics")
    for category, rows in sorted(category_rows.items()):
        print(category, average_metrics(rows))
    print("failures")
    for recall, case_id, query, gold, actual in sorted(failures):
        print(f"\n{case_id} recall@5={recall:.3f} {query}")
        print("  GOLD")
        for item in gold:
            print("   ", item)
        print("  TOP5")
        for item in actual:
            print("   ", item)
    session.close()


if __name__ == "__main__":
    main()
