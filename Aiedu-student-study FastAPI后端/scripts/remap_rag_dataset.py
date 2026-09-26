from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import CourseResource, ResourceChunk


def _normalized_ngrams(text: str, size: int = 5) -> set[str]:
    value = re.sub(
        r"www\.[a-z0-9.-]+\.[a-z]{2,}|Linux公社\s*\(LinuxIDC\.com\).*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\s+", "", value.lower())
    if len(value) <= size:
        return {value} if value else set()
    return {value[index:index + size] for index in range(len(value) - size + 1)}


def _overlap_score(old_text: str, new_text: str) -> float:
    old = _normalized_ngrams(old_text)
    new = _normalized_ngrams(new_text)
    if not old or not new:
        return 0.0
    common = len(old & new)
    containment = common / min(len(old), len(new))
    jaccard = common / len(old | new)
    return 0.7 * containment + 0.3 * jaccard


def snapshot(source: Path, output: Path, offering_id: int) -> None:
    payload = json.loads(source.read_text(encoding="utf-8"))
    with SessionLocal() as db:
        rows = db.execute(
            select(ResourceChunk, CourseResource.title)
            .join(CourseResource, CourseResource.id == ResourceChunk.resource_id)
            .where(
                ResourceChunk.offering_id == offering_id,
                CourseResource.deleted_at.is_(None),
            )
        ).all()
    chunks = {(title, chunk.content_hash): chunk for chunk, title in rows}
    references = []
    for case in payload["cases"]:
        for reference in case.get("relevant_chunks", []):
            key = (reference["resource_title"], reference["content_hash"])
            chunk = chunks.get(key)
            if chunk is None:
                raise ValueError(f"找不到旧金标准切片：{case['id']}:{key}")
            references.append({
                "case_id": case["id"],
                "resource_title": key[0],
                "old_content_hash": key[1],
                "relevance": reference["relevance"],
                "page_number": chunk.page_number,
                "slide_number": chunk.slide_number,
                "text": chunk.text,
            })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "source": str(source),
        "offering_id": offering_id,
        "references": references,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"snapshot": str(output), "references": len(references)}, ensure_ascii=False))


def remap(
    source: Path, snapshot_path: Path, output: Path, offering_id: int,
    dataset_version: str, minimum_score: float,
) -> None:
    payload = json.loads(source.read_text(encoding="utf-8"))
    saved = json.loads(snapshot_path.read_text(encoding="utf-8"))
    by_case: dict[str, list[dict]] = defaultdict(list)
    for item in saved["references"]:
        by_case[item["case_id"]].append(item)
    with SessionLocal() as db:
        rows = db.execute(
            select(ResourceChunk, CourseResource.title)
            .join(CourseResource, CourseResource.id == ResourceChunk.resource_id)
            .where(
                ResourceChunk.offering_id == offering_id,
                CourseResource.deleted_at.is_(None),
            )
        ).all()
    candidates: dict[str, list[ResourceChunk]] = defaultdict(list)
    for chunk, title in rows:
        candidates[title].append(chunk)

    audit = []
    for case in payload["cases"]:
        mapped = []
        for old in by_case.get(case["id"], []):
            options = candidates[old["resource_title"]]
            ranked = sorted(
                ((_overlap_score(old["text"], chunk.text), chunk) for chunk in options),
                key=lambda value: value[0], reverse=True,
            )
            if not ranked or ranked[0][0] < minimum_score:
                best = ranked[0][0] if ranked else 0.0
                raise ValueError(
                    f"{case['id']} 无可靠映射：{old['resource_title']} score={best:.4f}"
                )
            score, chunk = ranked[0]
            mapped.append({
                "resource_title": old["resource_title"],
                "content_hash": chunk.content_hash,
                "relevance": old["relevance"],
            })
            audit.append({
                "case_id": case["id"],
                "resource_title": old["resource_title"],
                "old_content_hash": old["old_content_hash"],
                "new_content_hash": chunk.content_hash,
                "score": round(score, 4),
                "page_number": chunk.page_number,
                "heading_path": chunk.heading_path,
                "text_preview": chunk.text[:240],
            })
        if mapped:
            case["relevant_chunks"] = mapped
    payload["version"] = dataset_version
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    audit_path = output.with_name(f"{output.stem}-remap-audit.json")
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "dataset": str(output), "audit": str(audit_path),
        "references": len(audit),
        "minimum_score": min(item["score"] for item in audit),
    }, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Snapshot and remap RAG gold chunk hashes after reindexing")
    parser.add_argument("mode", choices=("snapshot", "remap"))
    parser.add_argument("--source", type=Path, default=Path("evals/v1/rag.json"))
    parser.add_argument("--snapshot", type=Path, default=Path("evals/results/rag-gold-snapshot.json"))
    parser.add_argument("--output", type=Path, default=Path("evals/v2/rag.json"))
    parser.add_argument("--offering-id", type=int, default=2)
    parser.add_argument("--dataset-version", default="v2")
    parser.add_argument("--minimum-score", type=float, default=0.35)
    args = parser.parse_args()
    if args.mode == "snapshot":
        snapshot(args.source, args.snapshot, args.offering_id)
    else:
        remap(
            args.source, args.snapshot, args.output, args.offering_id,
            args.dataset_version, args.minimum_score,
        )


if __name__ == "__main__":
    main()
