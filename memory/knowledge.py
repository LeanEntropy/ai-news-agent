"""Knowledge extraction and retrieval for persistent agent memory."""

import json
import logging

from memory.store import Database

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Analyze this conversation and extract knowledge items the agent should remember for future interactions.

Extract ONLY concrete facts, NOT conversation flow or pleasantries. Categories:
- user_fact: Facts about the user (role, skills, constraints)
- project_update: Changes to user's projects (new project, dropped project, tech change)
- preference: Expressed likes/dislikes about content types, sources, topics
- tool_opinion: Opinions on specific tools, frameworks, services
- topic_interest: Topics the user showed interest in or asked about

Conversation:
{conversation}

Return a JSON array (empty if nothing worth extracting):
[{{"category": "<category>", "content": "<concise fact>"}}]
"""


class KnowledgeManager:
    def __init__(self, db: Database):
        self.db = db

    async def store_items(self, items: list[dict]):
        """Store extracted knowledge items."""
        for item in items:
            category = item.get("category", "user_fact")
            content = item.get("content", "")
            if content:
                await self.db.insert_knowledge(category, content, source="conversation")

    async def get_relevant(self, limit: int = 15) -> list[dict]:
        """Get top knowledge items by importance."""
        items = await self.db.get_top_knowledge(limit)
        # Touch accessed items to prevent decay
        for item in items:
            await self.db.touch_knowledge(item["id"])
        return items

    async def format_for_prompt(self, limit: int = 15) -> str:
        """Format knowledge items as text for system prompt injection."""
        items = await self.get_relevant(limit)
        if not items:
            return ""
        lines = ["Known facts about the user:"]
        for item in items:
            lines.append(f"- [{item['category']}] {item['content']}")
        return "\n".join(lines)

    def get_extraction_prompt(self, conversation_text: str) -> str:
        """Build the prompt to extract knowledge from a conversation."""
        return EXTRACTION_PROMPT.format(conversation=conversation_text)
