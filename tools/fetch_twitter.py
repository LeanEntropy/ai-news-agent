import logging

import feedparser
import httpx

logger = logging.getLogger(__name__)


async def fetch_twitter(
    accounts: list[str], rsshub_url: str = "https://rsshub.app"
) -> list[dict]:
    """Fetch tweets from accounts via RSSHub.

    Requires a running RSSHub instance (self-hosted or public).
    Set up via docker-compose or use a public instance.

    Args:
        accounts: List of Twitter handles (with or without @).
        rsshub_url: Base URL of RSSHub instance.
    """
    all_articles = []

    async with httpx.AsyncClient(timeout=20) as client:
        for account in accounts:
            handle = account.lstrip("@")
            try:
                url = f"{rsshub_url}/twitter/user/{handle}"
                response = await client.get(url)
                response.raise_for_status()
                parsed = feedparser.parse(response.text)

                for entry in parsed.entries[:10]:
                    all_articles.append({
                        "title": entry.get("title", "")[:200],
                        "url": entry.get("link", ""),
                        "content": entry.get("summary", "")[:1000],
                        "source_name": f"@{handle}",
                        "source_type": "twitter",
                        "category": "ai_news",
                        "published_at": "",
                    })
            except Exception as e:
                logger.warning(f"Failed to fetch tweets from @{handle}: {e}")

    logger.info(f"Fetched {len(all_articles)} tweets from {len(accounts)} accounts")
    return all_articles


TOOL_SCHEMA = {
    "name": "fetch_twitter",
    "description": "Fetch recent tweets from tracked Twitter/X accounts via RSSHub.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}
