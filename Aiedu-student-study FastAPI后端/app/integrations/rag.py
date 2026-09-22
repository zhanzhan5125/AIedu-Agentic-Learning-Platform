from __future__ import annotations

import hashlib
import io
import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings


@dataclass(frozen=True)
class DocumentBlock:
    block_type: str
    text: str
    heading_path: str | None = None
    page_number: int | None = None
    slide_number: int | None = None


def extract_blocks(content: bytes, mime_type: str) -> tuple[list[DocumentBlock], int | None]:
    """Extract format-aware blocks while retaining citation locators."""
    blocks: list[DocumentBlock] = []
    if mime_type == "application/pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        for page_number, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or "").strip()
            for paragraph in re.split(r"\n\s*\n+", text):
                value = " ".join(line.strip() for line in paragraph.splitlines() if line.strip())
                if value:
                    blocks.append(DocumentBlock("paragraph", value, page_number=page_number))
        return blocks, len(reader.pages)
    if mime_type.endswith("wordprocessingml.document"):
        from docx import Document

        document = Document(io.BytesIO(content))
        headings: list[str] = []
        for paragraph in document.paragraphs:
            value = paragraph.text.strip()
            if not value:
                continue
            style = (paragraph.style.name or "").lower() if paragraph.style else ""
            if style.startswith("heading") or style.startswith("标题"):
                match = re.search(r"(\d+)$", style)
                level = int(match.group(1)) if match else 1
                headings = headings[:max(0, level - 1)] + [value]
                blocks.append(DocumentBlock("heading", value, " > ".join(headings)))
            else:
                block_type = "list" if "list" in style or "列表" in style else "paragraph"
                blocks.append(DocumentBlock(block_type, value, " > ".join(headings) or None))
        for table in document.tables:
            rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
            value = "\n".join(row for row in rows if row.strip(" |"))
            if value:
                blocks.append(DocumentBlock("table", value, " > ".join(headings) or None))
        return blocks, None
    if mime_type.endswith("presentationml.presentation"):
        from pptx import Presentation

        presentation = Presentation(io.BytesIO(content))
        for slide_number, slide in enumerate(presentation.slides, 1):
            title = ""
            if slide.shapes.title is not None:
                title = (slide.shapes.title.text or "").strip()
            values: list[str] = []
            for shape in slide.shapes:
                if shape is slide.shapes.title:
                    continue
                if getattr(shape, "has_table", False):
                    rows = [" | ".join(cell.text.strip() for cell in row.cells)
                            for row in shape.table.rows]
                    table_text = "\n".join(row for row in rows if row.strip(" |"))
                    if table_text:
                        values.append(table_text)
                elif hasattr(shape, "text") and shape.text.strip():
                    values.append(shape.text.strip())
            text = "\n".join(values).strip()
            if title:
                blocks.append(DocumentBlock("heading", title, title, slide_number=slide_number))
            if text:
                blocks.append(DocumentBlock("slide", text, title or None, slide_number=slide_number))
        return blocks, len(presentation.slides)
    raise ValueError("不支持的课程资料类型")


def extract_text(content: bytes, mime_type: str) -> tuple[str, int | None]:
    blocks, page_count = extract_blocks(content, mime_type)
    return "\n\n".join(block.text for block in blocks), page_count


def _estimated_tokens(text: str) -> int:
    # Chinese is close to one token per character; latin text is closer to 4 chars/token.
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    return chinese + max(1, (len(text) - chinese) // 4)


def _prefix_for_tokens(text: str, token_limit: int) -> int:
    low, high = 1, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if _estimated_tokens(text[:middle]) <= token_limit:
            low = middle
        else:
            high = middle - 1
    return low


def _suffix_for_tokens(text: str, token_limit: int) -> str:
    if token_limit <= 0:
        return ""
    if _estimated_tokens(text) <= token_limit:
        return text
    low, high = 1, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if _estimated_tokens(text[-middle:]) <= token_limit:
            low = middle
        else:
            high = middle - 1
    return text[-low:].lstrip()


def _token_bounded_parts(text: str, maximum: int, overlap: int) -> list[str]:
    remaining = text.strip()
    values: list[str] = []
    while remaining:
        if _estimated_tokens(remaining) <= maximum:
            values.append(remaining)
            break
        end = _prefix_for_tokens(remaining, maximum)
        lower = max(1, end * 3 // 5)
        boundaries = [remaining.rfind(mark, lower, end) for mark in ("\n", "。", "！", "？", ". ", "; ")]
        natural = max(boundaries)
        if natural >= lower:
            end = natural + 1
        value = remaining[:end].strip()
        values.append(value)
        tail = _suffix_for_tokens(value, overlap)
        remaining = (tail + remaining[end:]).strip()
        if remaining == value:
            remaining = remaining[end:].strip()
    return values


def chunk_blocks(blocks: Sequence[DocumentBlock]) -> list[dict[str, Any]]:
    """Create section-aware chunks with bounded overlap and stable locator metadata."""
    settings = get_settings()
    target = settings.rag_chunk_target_tokens
    maximum = settings.rag_chunk_max_tokens
    overlap = settings.rag_chunk_overlap_tokens
    output: list[dict[str, Any]] = []
    current: list[str] = []
    current_tokens = 0
    meta: DocumentBlock | None = None

    def flush() -> None:
        nonlocal current, current_tokens, meta
        if not current or meta is None:
            return
        text = "\n\n".join(current).strip()
        if text:
            output.append({**asdict(meta), "text": text, "token_count": _estimated_tokens(text)})
        tail = _suffix_for_tokens(text, overlap)
        current = [tail] if tail else []
        current_tokens = _estimated_tokens(tail) if tail else 0

    for block in blocks:
        paragraphs = [value.strip() for value in re.split(r"\n\s*\n+", block.text) if value.strip()]
        if not paragraphs:
            continue
        if meta is not None and (block.heading_path != meta.heading_path or
                                 block.page_number != meta.page_number or
                                 block.slide_number != meta.slide_number) and current_tokens >= target // 2:
            flush()
            current = []
            current_tokens = 0
        meta = block
        for paragraph in paragraphs:
            parts = _token_bounded_parts(paragraph, max(1, maximum - overlap), 0)
            for part in parts:
                part_tokens = _estimated_tokens(part)
                if current and current_tokens + part_tokens > maximum:
                    flush()
                    meta = block
                current.append(part)
                current_tokens += part_tokens
                if current_tokens >= target:
                    flush()
                    meta = block
    flush()
    return output


def chunks(text: str, size: int | None = None, overlap: int | None = None) -> Iterable[str]:
    """Split at natural boundaries where possible and retain semantic overlap."""
    settings = get_settings()
    size = size or settings.rag_chunk_size_chars
    overlap = settings.rag_chunk_overlap_chars if overlap is None else overlap
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("切片大小配置无效")

    normalized = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n").replace("\r", "\n"))
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    start = 0
    while start < len(normalized):
        end = min(start + size, len(normalized))
        if end < len(normalized):
            lower_bound = start + max(size // 2, 1)
            candidates = [
                normalized.rfind("\n\n", lower_bound, end),
                normalized.rfind("。", lower_bound, end),
                normalized.rfind("！", lower_bound, end),
                normalized.rfind("？", lower_bound, end),
                normalized.rfind(". ", lower_bound, end),
            ]
            boundary = max(candidates)
            if boundary >= lower_bound:
                end = boundary + (1 if normalized[boundary] != "\n" else 2)
        value = normalized[start:end].strip()
        if value:
            yield value
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap)


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Call an OpenAI-compatible embeddings endpoint in bounded batches."""
    settings = get_settings()
    if not settings.ai_api_key:
        raise RuntimeError("尚未配置 AIEDU_AI_API_KEY，资料已保存，可配置后重新索引")
    if settings.embedding_model != "text-embedding-3-large":
        raise RuntimeError("课程知识库当前仅允许使用 text-embedding-3-large")

    from openai import OpenAI

    client = OpenAI(
        api_key=settings.ai_api_key,
        base_url=settings.ai_base_url,
        timeout=60,
        max_retries=3,
    )
    vectors: list[list[float]] = []
    batch_size = max(1, settings.embedding_batch_size)
    for offset in range(0, len(texts), batch_size):
        batch = list(texts[offset:offset + batch_size])
        response = client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
            dimensions=settings.embedding_dimensions,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        if len(ordered) != len(batch):
            raise RuntimeError("Embedding 服务返回的向量数量不匹配")
        for item in ordered:
            vector = list(item.embedding)
            if len(vector) != settings.embedding_dimensions:
                raise RuntimeError("Embedding 服务返回的向量维度不匹配")
            vectors.append(vector)
    return vectors


def _qdrant_client(timeout: int = 10):
    from qdrant_client import QdrantClient

    return QdrantClient(url=get_settings().qdrant_url, timeout=timeout)


def _ensure_collection(client) -> None:
    from qdrant_client import models

    settings = get_settings()
    collections = {item.name for item in client.get_collections().collections}
    if settings.qdrant_collection not in collections:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=models.VectorParams(
                size=settings.embedding_dimensions,
                distance=models.Distance.COSINE,
            ),
        )
        return
    collection = client.get_collection(settings.qdrant_collection)
    actual_size = getattr(collection.config.params.vectors, "size", None)
    if actual_size != settings.embedding_dimensions:
        raise RuntimeError(
            f"Qdrant 集合向量维度为 {actual_size}，配置要求 {settings.embedding_dimensions}，请更换集合名后重试"
        )


def index_resource(
    resource_id: int, offering_id: int, title: str,
    text: str | None = None, indexed_chunks: Sequence[dict[str, Any]] | None = None,
) -> int:
    from qdrant_client import models

    settings = get_settings()
    if indexed_chunks is None:
        values = [{"text": value, "position": position}
                  for position, value in enumerate(chunks(text or ""))]
    else:
        values = list(indexed_chunks)
    if not values:
        raise ValueError("资料未提取到可索引文本")

    # Do not delete a usable old index until every new vector exists.
    vectors = embed_texts([str(item["text"]) for item in values])
    client = _qdrant_client()
    _ensure_collection(client)
    points = []
    for position, (item, vector) in enumerate(zip(values, vectors, strict=True)):
        value = str(item["text"])
        point_id = int.from_bytes(
            hashlib.sha256(f"{resource_id}:{position}".encode()).digest()[:8], "big"
        ) >> 1
        points.append(models.PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "resource_id": resource_id,
                "offering_id": offering_id,
                "title": title,
                "position": position,
                "text": value,
                "chunk_id": item.get("id"),
                "block_type": item.get("block_type", "paragraph"),
                "heading_path": item.get("heading_path"),
                "page_number": item.get("page_number"),
                "slide_number": item.get("slide_number"),
                "embedding_model": settings.embedding_model,
            },
        ))
    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=models.FilterSelector(filter=models.Filter(must=[
            models.FieldCondition(key="resource_id", match=models.MatchValue(value=resource_id))
        ])),
        wait=True,
    )
    client.upsert(collection_name=settings.qdrant_collection, points=points, wait=True)
    return len(points)


def _tokenize(text: str) -> list[str]:
    normalized = re.sub(r"\s+", "", text.lower())
    latin = re.findall(r"[a-z0-9_]+", normalized)
    chinese = re.findall(r"[\u4e00-\u9fff]", normalized)
    bigrams = ["".join(chinese[index:index + 2]) for index in range(max(0, len(chinese) - 1))]
    return latin + chinese + bigrams


def _bm25_search(db: Session, offering_id: int, query: str, limit: int) -> list[dict]:
    from app.models import CourseResource, ResourceChunk

    rows = db.execute(
        select(ResourceChunk, CourseResource.title)
        .join(CourseResource, CourseResource.id == ResourceChunk.resource_id)
        .where(ResourceChunk.offering_id == offering_id, CourseResource.deleted_at.is_(None))
        .order_by(ResourceChunk.id)
    ).all()
    if not rows:
        return []
    documents = [_tokenize(chunk.text) for chunk, _ in rows]
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []
    document_frequency: Counter[str] = Counter()
    for tokens in documents:
        document_frequency.update(set(tokens))
    average_length = sum(len(tokens) for tokens in documents) / max(1, len(documents))
    scored: list[tuple[float, Any, str]] = []
    for (chunk, title), tokens in zip(rows, documents, strict=True):
        frequencies = Counter(tokens)
        score = 0.0
        for token in query_tokens:
            frequency = frequencies[token]
            if not frequency:
                continue
            idf = math.log(1 + (len(documents) - document_frequency[token] + 0.5) /
                           (document_frequency[token] + 0.5))
            denominator = frequency + 1.5 * (1 - 0.75 + 0.75 * len(tokens) / max(1, average_length))
            score += idf * frequency * 2.5 / denominator
        if score > 0:
            scored.append((score, chunk, title))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [_chunk_result(chunk, title, round(score, 4), "bm25")
            for score, chunk, title in scored[:limit]]


def _chunk_result(chunk, title: str, score: float, source: str) -> dict:
    return {
        "chunk_id": chunk.id,
        "resource_id": chunk.resource_id,
        "title": title,
        "position": chunk.position,
        "text": chunk.text,
        "score": score,
        "retrieval_source": source,
        "block_type": chunk.block_type,
        "heading_path": chunk.heading_path,
        "page_number": chunk.page_number,
        "slide_number": chunk.slide_number,
    }


def _dense_search(offering_id: int, query: str, limit: int) -> list[dict]:
    from qdrant_client import models

    settings = get_settings()
    try:
        query_vector = embed_texts([query])[0]
        result = _qdrant_client(timeout=5).query_points(
            collection_name=settings.qdrant_collection,
            query=query_vector,
            query_filter=models.Filter(must=[
                models.FieldCondition(key="offering_id", match=models.MatchValue(value=offering_id))
            ]),
            limit=limit,
        ).points
    except Exception:
        return []
    return [{
        "chunk_id": item.payload.get("chunk_id"),
        "resource_id": item.payload["resource_id"],
        "title": item.payload["title"],
        "position": item.payload["position"],
        "text": item.payload["text"],
        "score": round(float(item.score), 4),
        "retrieval_source": "dense",
        "block_type": item.payload.get("block_type", "paragraph"),
        "heading_path": item.payload.get("heading_path"),
        "page_number": item.payload.get("page_number"),
        "slide_number": item.payload.get("slide_number"),
    } for item in result]


def _rrf(dense: Sequence[dict], lexical: Sequence[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for source in (dense, lexical):
        for rank, item in enumerate(source):
            key = str(item.get("chunk_id") or f'{item["resource_id"]}:{item["position"]}')
            if key not in merged:
                merged[key] = {**item, "rrf_score": 0.0, "retrieval_sources": []}
            merged[key]["rrf_score"] += 1 / (60 + rank + 1)
            merged[key]["retrieval_sources"].append(item["retrieval_source"])
            if item["retrieval_source"] == "dense":
                merged[key]["score"] = item["score"]
    return sorted(merged.values(), key=lambda item: item["rrf_score"], reverse=True)


@lru_cache(maxsize=1)
def _load_reranker():
    if not get_settings().enable_local_reranker:
        return None
    try:
        from sentence_transformers import CrossEncoder

        return CrossEncoder(get_settings().reranker_model, max_length=512)
    except Exception:
        return None


def _rerank(query: str, candidates: list[dict]) -> list[dict]:
    model = _load_reranker()
    if model is None or not candidates:
        return candidates
    try:
        scores = model.predict([(query, item["text"]) for item in candidates[:12]])
        for item, score in zip(candidates[:12], scores, strict=True):
            item["rerank_score"] = float(score)
        head = sorted(candidates[:12], key=lambda item: item["rerank_score"], reverse=True)
        return head + candidates[12:]
    except Exception:
        return candidates


def search_course(
    offering_id: int, query: str, limit: int = 5, db: Session | None = None,
) -> list[dict]:
    """Course-scoped dense + BM25 retrieval, fused with RRF and optional reranking."""
    from app.db import SessionLocal

    owns_session = db is None
    session = db or SessionLocal()
    try:
        dense = _dense_search(offering_id, query, 20)
        lexical = _bm25_search(session, offering_id, query, 20)
        results = _rerank(query, _rrf(dense, lexical))
        return results[:limit]
    finally:
        if owns_session:
            session.close()


def delete_resource_vectors(resource_id: int) -> None:
    from qdrant_client import models

    settings = get_settings()
    try:
        _qdrant_client(timeout=5).delete(
            collection_name=settings.qdrant_collection,
            points_selector=models.FilterSelector(filter=models.Filter(must=[
                models.FieldCondition(key="resource_id", match=models.MatchValue(value=resource_id))
            ])),
            wait=True,
        )
    except Exception:
        return
