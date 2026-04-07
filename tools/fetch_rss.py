import logging
from datetime import datetime, timezone

import feedparser
import httpx

logger = logging.getLogger(__name__)


async def fetch_rss(feeds: list[dict]) -> list[dict]:
    """Fetch articles from RSS feeds.

    Args:
        feeds: List of dicts with 'name', 'url', 'category' keys.

    Returns:
        List of article dicts.
    """
    all_articles = []

    async with httpx.AsyncClient(timeout=20) as client:
        for feed_config in feeds:
            try:
                response = await client.get(
                    feed_config["url"],
                    headers={"User-Agent": "AINewsAgent/1.0"},
                )
                response.raise_for_status()
                parsed = feedparser.parse(response.text)

                for entry in parsed.entries[:20]:  # Cap per feed
                    published = ""
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        try:
                            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()
                        except Exception:
                            pass

                    all_articles.append({
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "content": entry.get("summary", ""),
                        "source_name": feed_config["name"],
                        "source_type": "rss",
                        "category": feed_config.get("category", "general_ai"),
                        "published_at": published,
                    })
            except Exception as e:
                logger.warning(f"Failed to fetch RSS feed {feed_config['name']}: {e}")

    logger.info(f"Fetched {len(all_articles)} articles from {len(feeds)} RSS feeds")
    return all_articles


TOOL_SCHEMA = {
    "name": "fetch_rss",
    "description": "Fetch latest articles from configured RSS feeds. Returns recent articles from AI news, tech blogs, and other configured sources.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}
