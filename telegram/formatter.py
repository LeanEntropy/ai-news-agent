"""Format digests and messages for Telegram."""

from datetime import datetime, timezone


def format_digest(items: list[dict], period: str = "morning") -> list[str]:
    """Format digest items into Telegram messages.

    Returns a list of messages (split to stay under Telegram's 4096 char limit).
    """
    now = datetime.now(timezone.utc).strftime("%b %d, %Y")
    label = "MORNING BRIEFING" if period == "morning" else "EVENING UPDATE"

    sections = {
        "top_news": {"header": "TOP NEWS", "emoji": "", "items": []},
        "game_dev_ai": {"header": "AI + GAME DEV", "emoji": "", "items": []},
        "project_relevant": {"header": "FOR YOUR PROJECTS", "emoji": "", "items": []},
        "general_ai": {"header": "NOTABLE", "emoji": "", "items": []},
    }

    for item in items:
        cat = item.get("category", "general_ai").lower()
        if cat in sections:
            sections[cat]["items"].append(item)

    lines = [f"*{label} \\- {_escape(now)}*\n"]

    for cat_key, section in sections.items():
        if not section["items"]:
            continue

        lines.append(f"*{_escape(section['header'])}*")
        lines.append(_escape("━" * 20))

        for item in section["items"][:5]:
            title = item.get("title", item.get("summary", "")[:80])
            summary = item.get("summary", "")
            url = item.get("url", "")
            score = item.get("importance_score", 0)
            project_rel = item.get("project_relevance", "")

            lines.append(f"[{_escape(title)}]({url})")
            if summary:
                lines.append(_escape(summary))
            if project_rel and cat_key == "project_relevant":
                lines.append(f"_{_escape('Why: ' + project_rel)}_")
            lines.append("")

    # Stats
    total = sum(len(s["items"]) for s in sections.values())
    lines.append(_escape(f"---\n{total} items surfaced | Reply to chat | /search"))

    # Split into messages under 4096 chars
    return _split_messages(lines)


def format_discovery(discovery: dict) -> str:
    """Format a single discovery for Telegram."""
    title = discovery.get("title", "")
    url = discovery.get("url", "")
    desc = discovery.get("description", "")
    reasoning = discovery.get("reasoning", "")
    project = discovery.get("project_name", "")

    lines = [
        f"*DISCOVERY*",
        f"[{_escape(title)}]({url})",
    ]
    if desc:
        lines.append(_escape(desc))
    if reasoning:
        lines.append(f"_{_escape('Why: ' + reasoning)}_")
    if project:
        lines.append(f"_{_escape('Project: ' + project)}_")

    return "\n".join(lines)


def format_stats(stats: dict) -> str:
    """Format agent stats for Telegram."""
    return (
        f"*Agent Status*\n"
        f"Articles collected: {stats.get('total_articles', 0)}\n"
        f"Articles delivered: {stats.get('delivered_articles', 0)}\n"
        f"Feedback received: {stats.get('total_feedback', 0)}\n"
        f"Discoveries made: {stats.get('total_discoveries', 0)}"
    )


def _escape(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = r"_*[]()~`>#+-=|{}.!"
    result = ""
    for char in text:
        if char in special:
            result += f"\\{char}"
        else:
            result += char
    return result


def _split_messages(lines: list[str], max_length: int = 4000) -> list[str]:
    """Split lines into messages under max_length."""
    messages = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > max_length:
            if current:
                messages.append(current)
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        messages.append(current)
    return messages or ["No news to report."]
