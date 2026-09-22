from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db import SessionLocal
from app.integrations.rag import _bm25_search, _dense_search, _rrf, _rerank


def hit_rank(results: list[dict], terms: list[str]) -> int | None:
    for index, item in enumerate(results, 1):
        text = f"{item.get('heading_path') or ''} {item.get('text') or ''}".lower()
        if any(term.lower() in text for term in terms):
            return index
    return None


def metrics(ranks: list[int | None], k: int) -> dict:
    return {
        f"hit@{k}": round(sum(rank is not None and rank <= k for rank in ranks) / len(ranks), 4),
        "mrr": round(sum(1 / rank for rank in ranks if rank) / len(ranks), 4),
        "cases": len(ranks),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Dense and Hybrid+Rerank on a course offering")
    parser.add_argument("--offering-id", type=int, required=True)
    parser.add_argument("--cases", type=Path, default=Path(__file__).parents[1] / "evals" / "rag_cases.json")
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    dense_ranks: list[int | None] = []
    hybrid_ranks: list[int | None] = []
    with SessionLocal() as db:
        for case in cases:
            dense = _dense_search(args.offering_id, case["query"], 6)
            lexical = _bm25_search(db, args.offering_id, case["query"], 20)
            hybrid = _rerank(case["query"], _rrf(_dense_search(args.offering_id, case["query"], 20), lexical))[:6]
            dense_ranks.append(hit_rank(dense, case["expected_terms"]))
            hybrid_ranks.append(hit_rank(hybrid, case["expected_terms"]))
    print(json.dumps({"dense": metrics(dense_ranks, 6),
                      "hybrid_rerank": metrics(hybrid_ranks, 6)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
