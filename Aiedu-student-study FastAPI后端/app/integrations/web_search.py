from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import get_settings


def web_search(query: str, limit: int = 3) -> list[dict]:
    """Small Tavily-compatible read-only provider. Returned pages are untrusted evidence."""
    settings = get_settings()
    if not settings.tavily_api_key:
        return []
    import httpx
    response = httpx.post(
        settings.tavily_base_url,
        json={
            "api_key": settings.tavily_api_key,
            "query": query,
            "max_results": min(max(1, limit), 5),
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
        },
        timeout=15,
    )
    response.raise_for_status()
    fetched_at = datetime.now(timezone.utc).isoformat()
    return [{
        "title": item.get("title") or item.get("url") or "网页资料",
        "url": item.get("url"),
        "excerpt": (item.get("content") or "")[:1200],
        "score": item.get("score"),
        "fetched_at": fetched_at,
    } for item in response.json().get("results", [])[:limit]]
