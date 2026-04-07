import logging

from memory.store import Database

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Manages conversation history for agent context."""

    def __init__(self, db: Database, max_messages: int = 30):
        self.db = db
        self.max_messages = max_messages

    async def add(self, role: str, content: str):
        await self.db.add_conversation_message(role, content)

    async def get_context(self) -> list[dict]:
        """Get recent conversation history for agent context."""
        return await self.db.get_recent_conversations(self.max_messages)
