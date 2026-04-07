import logging

import httpx

logger = logging.getLogger(__name__)

HN_API = "https://hacker-news.firebaseio.com/v0"


async def fetch_hackernews(
    story_type: str = "top",
    keywords: list[str] | None = None,
    max_results: int = 30,
) -> list[dict]:
    """Fetch stories from Hacker News, optionally filtered by keywords."""
    endpoint = {"top": "topstories", "best": "beststories", "new": "newstories"}.get(
        story_type, "topstories"
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{HN_API}/{endpoint}.json")
            response.raise_for_status()
            story_ids = response.json()[:100]  # Check top 100

            articles = []
            for story_id in story_ids:
                if len(articles) >= max_results:
                    break

                resp = await client.get(f"{HN_API}/item/{story_id}.json")
                if resp.status_code != 200:
                    continue
                story = resp.json()
                if not story or story.get("type") != "story":
                    continue

                title = story.get("title", "")
                url = story.get("url", f"https://news.ycombinator.com/item?id={story_id}")

                # Keyword filter
                if keywords:
                    title_lower = title.lower()
                    if not any(kw.lower() in title_lower for kw in keywords):
                        continue

                articles.append({
                    "title": title,
                    "url": url,
                    "content": "",
                    "source_name": "Hacker News",
                    "source_type": "hackernews",
                    "score": story.get("score", 0),
                    "comments": story.get("descendants", 0),
                    "published_at": "",
                })

        logger.info(f"Fetched {len(articles)} stories from HN ({story_type})")
        return articles
    except Exception as e:
        logger.error(f"HN fetch failed: {e}")
        return []


TOOL_SCHEMA = {
    "name": "fetch_hackernews",
    "description": "Fetch top stories from Hacker News, optionally filtered by AI/tech keywords.",
    "parameters": {
        "type": "object",
        "properties": {
            "story_type": {
                "type": "string",
                "enum": ["top", "best", "new"],
                "description": "Type of stories (default: top)",
                "default": "top",
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter stories containing these keywords",
            },
        },
    },
}
