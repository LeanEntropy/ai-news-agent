import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _headers() -> dict:
    h = {"Accept": "application/vnd.github.v3+json"}
    if settings.GITHUB_TOKEN:
        h["Authorization"] = f"token {settings.GITHUB_TOKEN}"
    return h


async def search_github(
    query: str,
    sort: str = "stars",
    order: str = "desc",
    max_results: int = 10,
    created_after: str = "",
) -> list[dict]:
    """Search GitHub repositories."""
    q = query
    if created_after:
        q += f" created:>{created_after}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{GITHUB_API}/search/repositories",
                params={"q": q, "sort": sort, "order": order, "per_page": max_results},
                headers=_headers(),
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for repo in data.get("items", []):
            results.append({
                "name": repo["full_name"],
                "url": repo["html_url"],
                "description": repo.get("description") or "",
                "stars": repo["stargazers_count"],
                "language": repo.get("language") or "",
                "created_at": repo.get("created_at", ""),
                "updated_at": repo.get("updated_at", ""),
                "topics": repo.get("topics", []),
            })
        return results
    except Exception as e:
        logger.error(f"GitHub search failed: {e}")
        return []


async def get_trending(language: str = "", since: str = "daily") -> list[dict]:
    """Get trending repos via GitHub search (sorted by stars, created recently)."""
    from datetime import datetime, timedelta, timezone

    days = {"daily": 1, "weekly": 7, "monthly": 30}.get(since, 1)
    date_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    query = f"stars:>10 created:>{date_cutoff}"
    if language:
        query += f" language:{language}"

    return await search_github(query, sort="stars", max_results=10)


async def get_repo_releases(owner_repo: str, max_results: int = 5) -> list[dict]:
    """Get recent releases for a repo."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{GITHUB_API}/repos/{owner_repo}/releases",
                params={"per_page": max_results},
                headers=_headers(),
            )
            response.raise_for_status()
            releases = response.json()

        return [
            {
                "tag": r.get("tag_name", ""),
                "name": r.get("name", ""),
                "url": r.get("html_url", ""),
                "published_at": r.get("published_at", ""),
                "body": (r.get("body") or "")[:500],
            }
            for r in releases
        ]
    except Exception as e:
        logger.error(f"Failed to get releases for {owner_repo}: {e}")
        return []


async def get_org_recent_repos(org: str, max_results: int = 5) -> list[dict]:
    """Get recently updated repos from an org."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{GITHUB_API}/orgs/{org}/repos",
                params={"sort": "updated", "per_page": max_results, "type": "public"},
                headers=_headers(),
            )
            response.raise_for_status()
            repos = response.json()

        results = []
        for repo in repos:
            results.append({
                "name": repo["full_name"],
                "url": repo["html_url"],
                "description": repo.get("description") or "",
                "stars": repo["stargazers_count"],
                "language": repo.get("language") or "",
                "updated_at": repo.get("updated_at", ""),
            })
        return results
    except Exception as e:
        logger.error(f"Failed to get repos for org {org}: {e}")
        return []


TOOL_SCHEMA = {
    "name": "search_github",
    "description": "Search GitHub for repositories, trending projects, and releases. Use to find new tools, libraries, MCP servers, and repos relevant to specific topics or projects.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (e.g., 'mcp server unity', 'ai agent memory')",
            },
            "sort": {
                "type": "string",
                "enum": ["stars", "updated", "created"],
                "description": "Sort by (default: stars)",
                "default": "stars",
            },
            "max_results": {
                "type": "integer",
                "description": "Max results (default 10)",
                "default": 10,
            },
            "created_after": {
                "type": "string",
                "description": "Only repos created after this date (YYYY-MM-DD)",
            },
        },
        "required": ["query"],
    },
}
