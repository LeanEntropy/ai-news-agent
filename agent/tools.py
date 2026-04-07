"""Tool registry - maps tool names to implementations and schemas."""

import json
import logging

from tools import search_web, search_github, browse_url
from tools import fetch_rss, fetch_hackernews, fetch_reddit, fetch_twitter

logger = logging.getLogger(__name__)

# All available tool schemas for the LLM
TOOL_SCHEMAS = [
    search_web.TOOL_SCHEMA,
    search_github.TOOL_SCHEMA,
    browse_url.TOOL_SCHEMA,
    fetch_rss.TOOL_SCHEMA,
    fetch_hackernews.TOOL_SCHEMA,
    fetch_reddit.TOOL_SCHEMA,
    fetch_twitter.TOOL_SCHEMA,
]


async def execute_tool(name: str, arguments: dict, sources_config: dict) -> str:
    """Execute a tool by name and return result as string."""
    try:
        if name == "search_web":
            result = await search_web.search_web(**arguments)
        elif name == "search_github":
            result = await search_github.search_github(**arguments)
        elif name == "browse_url":
            result = await browse_url.browse_url(**arguments)
        elif name == "fetch_rss":
            feeds = _get_all_rss_feeds(sources_config)
            result = await fetch_rss.fetch_rss(feeds)
        elif name == "fetch_hackernews":
            keywords = sources_config.get("hackernews", {}).get("keywords", [])
            args = {**arguments, "keywords": keywords}
            result = await fetch_hackernews.fetch_hackernews(**args)
        elif name == "fetch_reddit":
            subs = sources_config.get("reddit", {}).get("subreddits", [])
            result = await fetch_reddit.fetch_reddit(subs)
        elif name == "fetch_twitter":
            accounts = sources_config.get("twitter", {}).get("accounts", [])
            if not accounts:
                return json.dumps({"message": "No Twitter accounts configured"})
            result = await fetch_twitter.fetch_twitter(accounts)
        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

        return json.dumps(result, default=str)
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}")
        return json.dumps({"error": str(e)})


def _get_all_rss_feeds(sources_config: dict) -> list[dict]:
    """Flatten all RSS feed groups into a single list."""
    feeds = []
    rss_config = sources_config.get("rss", {})
    for group_name, group_feeds in rss_config.items():
        if isinstance(group_feeds, list):
            feeds.extend(group_feeds)
    return feeds
