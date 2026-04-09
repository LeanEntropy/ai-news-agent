import asyncio
import pytest
from pathlib import Path
from memory.store import Database
from memory.preference_engine import PreferenceEngine

@pytest.fixture
def db(tmp_path):
    db = Database(tmp_path / "test.db")
    asyncio.get_event_loop().run_until_complete(db.initialize())
    yield db
    asyncio.get_event_loop().run_until_complete(db.close())

def test_record_positive_signal(db):
    async def check():
        pe = PreferenceEngine(db)
        await pe.record_signal(
            signal_type="feedback_positive",
            topic="ComfyUI",
            source_name="r/comfyui",
            category="game_dev_ai",
            article_id=1,
        )
        topics = await db.get_topic_scores()
        assert "ComfyUI" in topics
        assert topics["ComfyUI"] > 0
    asyncio.get_event_loop().run_until_complete(check())

def test_record_negative_signal(db):
    async def check():
        pe = PreferenceEngine(db)
        await pe.record_signal(
            signal_type="feedback_negative",
            topic="AI policy",
            source_name="Ars Technica",
            category="general_ai",
            article_id=2,
        )
        topics = await db.get_topic_scores()
        assert topics["AI policy"] < 0
        sources = await db.get_source_scores()
        assert sources["Ars Technica"]["score"] < 0
    asyncio.get_event_loop().run_until_complete(check())

def test_format_for_scoring(db):
    async def check():
        pe = PreferenceEngine(db)
        await pe.record_signal("feedback_positive", topic="Godot", source_name="r/godot", article_id=1)
        await pe.record_signal("feedback_negative", topic="crypto", source_name="HN", article_id=2)
        text = await pe.format_for_scoring()
        assert "Godot" in text
        assert "crypto" in text
    asyncio.get_event_loop().run_until_complete(check())
