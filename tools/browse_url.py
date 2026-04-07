import logging

import httpx
import trafilatura

logger = logging.getLogger(__name__)


async def browse_url(url: str, max_length: int = 5000) -> dict:
    """Fetch a URL and extract clean text content."""
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "AINewsAgent/1.0"})
            response.raise_for_status()
            html = response.text

        text = trafilatura.extract(html, include_links=True, include_tables=True) or ""
        if len(text) > max_length:
            text = text[:max_length] + "..."

        return {
            "url": url,
            "text": text,
            "title": trafilatura.extract_metadata(html).title if trafilatura.extract_metadata(html) else "",
            "length": len(text),
        }
    except Exception as e:
        logger.error(f"Failed to browse {url}: {e}")
        return {"url": url, "text": "", "title": "", "error": str(e)}


TOOL_SCHEMA = {
    "name": "browse_url",
    "description": "Fetch a URL and extract its text content. Use for reading articles, blog posts, repo READMEs, or any web page in detail.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to fetch and extract content from",
            },
        },
        "required": ["url"],
    },
}
