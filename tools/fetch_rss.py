import logging
from datetime import datetime, timezone

import feedparser
import httpx

logger = logging.getLogger(__name__)


async def fetch_rss(feeds: list[dict], max_age_days: int = 7) -> list[dict]:
    """Fetch articles from RSS feeds, filtering to recent items only.

    Args:
        feeds: List of dicts with 'name', 'url', 'category' keys.
        max_age_days: Only include articles from the last N days.
    """
    from datetime import timedelta

    all_articles = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for feed_config in feeds:
            try:
                response = await client.get(
                    feed_config["url"],
                    headers={"User-Agent": "AINewsAgent/1.0"},
                )
                response.raise_for_status()
                parsed = feedparser.parse(response.text)

                for entry in parsed.entries[:20]:
                    published = ""
                    pub_dt = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        try:
                            pub_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                            published = pub_dt.isoformat()
                        except Exception:
                            pass
                    elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                        try:
                            pub_dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
                            published = pub_dt.isoformat()
                        except Exception:
                            pass

                    # Skip articles older than cutoff
                    if pub_dt and pub_dt < cutoff:
                        continue

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

    logger.info(f"Fetched {len(all_articles)} recent articles from {len(feeds)} RSS feeds")
    return all_articles


TOOL_SCHEMA = {
    "name": "fetch_rss",
    "description": "Fetch latest articles from configured RSS feeds. Returns recent articles from AI news, tech blogs, and other configured sources.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}
