"""Format digests and messages for Telegram."""

from datetime import datetime, timezone


def format_digest(items: list[dict], period: str = "morning") -> list[str]:
    """Format digest items into Telegram messages (HTML mode).

    Returns a list of messages (split to stay under Telegram's 4096 char limit).
    """
    now = datetime.now(timezone.utc).strftime("%b %d, %Y")
    label = "MORNING BRIEFING" if period == "morning" else "EVENING UPDATE"

    sections = {
        "top_news": {"header": "TOP NEWS", "items": []},
        "game_dev_ai": {"header": "AI + GAME DEV", "items": []},
        "project_relevant": {"header": "FOR YOUR PROJECTS", "items": []},
        "general_ai": {"header": "NOTABLE", "items": []},
    }

    for item in items:
        cat = item.get("category", "general_ai").lower()
        if cat in sections:
            sections[cat]["items"].append(item)

    lines = [f"<b>{label} - {_esc(now)}</b>\n"]

    for cat_key, section in sections.items():
        if not section["items"]:
            continue

        lines.append(f"<b>{_esc(section['header'])}</b>")
        lines.append("━" * 20)

        for item in section["items"][:5]:
            title = _esc(item.get("title", "")[:120])
            summary = _esc(item.get("summary", ""))
            url = item.get("url", "")
            project_rel = item.get("project_relevance", "")

            # Title as link if URL available
            if url:
                lines.append(f'<a href="{url}">{title}</a>')
            else:
                lines.append(f"<b>{title}</b>")

            # Summary (skip if it's just repeating the title)
            if summary and not _is_duplicate(title, summary):
                lines.append(summary)

            if project_rel and cat_key == "project_relevant":
                lines.append(f"<i>Why: {_esc(project_rel)}</i>")

            lines.append("")

    # Stats
    total = sum(len(s["items"]) for s in sections.values())
    lines.append(f"---\n{total} items surfaced | Reply to chat | /search")

    return _split_messages(lines)


def format_discovery(discovery: dict) -> str:
    """Format a single discovery for Telegram."""
    title = _esc(discovery.get("title", ""))
    url = discovery.get("url", "")
    desc = _esc(discovery.get("description", ""))
    reasoning = _esc(discovery.get("reasoning", ""))
    project = _esc(discovery.get("project_name", ""))

    lines = ["<b>DISCOVERY</b>"]
    if url:
        lines.append(f'<a href="{url}">{title}</a>')
    else:
        lines.append(f"<b>{title}</b>")
    if desc:
        lines.append(desc)
    if reasoning:
        lines.append(f"<i>Why: {reasoning}</i>")
    if project:
        lines.append(f"<i>Project: {project}</i>")

    return "\n".join(lines)


def format_stats(stats: dict) -> str:
    """Format agent stats for Telegram."""
    return (
        f"<b>Agent Status</b>\n"
        f"Articles collected: {stats.get('total_articles', 0)}\n"
        f"Articles delivered: {stats.get('delivered_articles', 0)}\n"
        f"Feedback received: {stats.get('total_feedback', 0)}\n"
        f"Discoveries made: {stats.get('total_discoveries', 0)}"
    )


def _esc(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _is_duplicate(title: str, summary: str) -> bool:
    """Check if summary is just repeating the title."""
    title_clean = title.lower().strip().rstrip(".")
    summary_clean = summary.lower().strip().rstrip(".")
    return (
        summary_clean.startswith(title_clean)
        or title_clean.startswith(summary_clean)
        or len(summary) < 20
    )


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
