import logging

import feedparser
import httpx

logger = logging.getLogger(__name__)


async def fetch_reddit(subreddits: list[dict], max_per_sub: int = 15) -> list[dict]:
    """Fetch posts from Reddit subreddits via RSS (no API key needed).

    Args:
        subreddits: List of dicts with 'name' and 'category' keys.
    """
    all_articles = []

    async with httpx.AsyncClient(timeout=20) as client:
        for sub in subreddits:
            try:
                url = f"https://www.reddit.com/r/{sub['name']}/hot/.rss"
                response = await client.get(
                    url, headers={"User-Agent": "AINewsAgent/1.0"}
                )
                response.raise_for_status()
                parsed = feedparser.parse(response.text)

                for entry in parsed.entries[:max_per_sub]:
                    all_articles.append({
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "content": entry.get("summary", "")[:1000],
                        "source_name": f"r/{sub['name']}",
                        "source_type": "reddit",
                        "category": sub.get("category", "general_ai"),
                        "published_at": "",
                    })
            except Exception as e:
                logger.warning(f"Failed to fetch r/{sub['name']}: {e}")

    logger.info(f"Fetched {len(all_articles)} posts from {len(subreddits)} subreddits")
    return all_articles


TOOL_SCHEMA = {
    "name": "fetch_reddit",
    "description": "Fetch recent posts from configured Reddit subreddits related to AI and game development.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}
