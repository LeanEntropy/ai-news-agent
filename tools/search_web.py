import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)


async def search_web(query: str, max_results: int = 10) -> list[dict]:
    """Search the web using Tavily API. Falls back to empty if no API key."""
    if not settings.TAVILY_API_KEY:
        logger.warning("No TAVILY_API_KEY set, web search unavailable")
        return []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.TAVILY_API_KEY,
                    "query": query,
                    "max_results": max_results,
                    "include_answer": False,
                },
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for r in data.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0),
            })
        return results
    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return []


TOOL_SCHEMA = {
    "name": "search_web",
    "description": "Search the web for current information, news, and articles. Use for finding recent events, announcements, and developments.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default 10)",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}
