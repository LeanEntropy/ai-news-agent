import asyncio
import pytest
from pathlib import Path
from memory.store import Database
from memory.knowledge import KnowledgeManager

@pytest.fixture
def db(tmp_path):
    db = Database(tmp_path / "test.db")
    asyncio.get_event_loop().run_until_complete(db.initialize())
    yield db
    asyncio.get_event_loop().run_until_complete(db.close())

def test_store_and_retrieve_knowledge(db):
    async def check():
        km = KnowledgeManager(db)
        await km.store_items([
            {"category": "user_fact", "content": "User is evaluating Rust for backend"},
            {"category": "tool_opinion", "content": "User likes ComfyUI for image gen"},
        ])
        items = await km.get_relevant(limit=10)
        assert len(items) == 2
        assert any("Rust" in i["content"] for i in items)
    asyncio.get_event_loop().run_until_complete(check())

def test_format_for_prompt(db):
    async def check():
        km = KnowledgeManager(db)
        await km.store_items([
            {"category": "user_fact", "content": "User works with Godot 4.6"},
        ])
        text = await km.format_for_prompt()
        assert "Godot" in text
        assert len(text) > 0
    asyncio.get_event_loop().run_until_complete(check())

def test_decay_removes_low_importance(db):
    async def check():
        km = KnowledgeManager(db)
        kid = await db.insert_knowledge("user_fact", "Old forgotten fact")
        # Manually set importance low
        await db.db.execute("UPDATE knowledge SET importance = 0.2, access_count = 0 WHERE id = ?", (kid,))
        await db.db.commit()
        await db.decay_knowledge(inactive_days=0)
        items = await km.get_relevant(limit=10)
        assert len(items) == 0
    asyncio.get_event_loop().run_until_complete(check())
