import asyncio
import pytest
from pathlib import Path
from memory.store import Database

@pytest.fixture
def db(tmp_path):
    db = Database(tmp_path / "test.db")
    asyncio.get_event_loop().run_until_complete(db.initialize())
    yield db
    asyncio.get_event_loop().run_until_complete(db.close())

def test_knowledge_table_exists(db):
    async def check():
        cursor = await db.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge'")
        row = await cursor.fetchone()
        assert row is not None
    asyncio.get_event_loop().run_until_complete(check())

def test_engagement_signals_table_exists(db):
    async def check():
        cursor = await db.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='engagement_signals'")
        row = await cursor.fetchone()
        assert row is not None
    asyncio.get_event_loop().run_until_complete(check())

def test_topic_scores_table_exists(db):
    async def check():
        cursor = await db.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='topic_scores'")
        row = await cursor.fetchone()
        assert row is not None
    asyncio.get_event_loop().run_until_complete(check())

def test_source_scores_table_exists(db):
    async def check():
        cursor = await db.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='source_scores'")
        row = await cursor.fetchone()
        assert row is not None
    asyncio.get_event_loop().run_until_complete(check())
