# Knowledge Memory & Adaptive Preference Engine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the agent persistent memory across sessions (knowledge extraction from conversations) and multi-signal preference learning (beyond just button clicks).

**Architecture:** Two new modules added to the existing `memory/` package. `knowledge.py` extracts facts from conversations via LLM and stores in SQLite with importance decay. `preference_engine.py` collects engagement signals from all interaction types (feedback, deep dives, conversation mentions, ignores) and maintains per-topic and per-source scores. Both are integrated into `agent/core.py` and injected into the system prompt.

**Tech Stack:** Python 3.12, aiosqlite, existing LLM provider abstraction, existing APScheduler.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `memory/store.py` | Modify | Add 4 new tables: knowledge, engagement_signals, topic_scores, source_scores |
| `memory/knowledge.py` | Create | Knowledge extraction, retrieval, and decay |
| `memory/preference_engine.py` | Create | Multi-signal preference learning, topic/source scoring |
| `agent/core.py` | Modify | Integrate knowledge extraction after conversations, inject knowledge into context, record engagement signals |
| `agent/prompts.py` | Modify | Add KNOWLEDGE_EXTRACTION_PROMPT, update build_system_prompt to include knowledge |
| `delivery/bot.py` | Modify | Record deep_dive signals, add /knowledge command |
| `tasks/scheduler.py` | Modify | Add daily knowledge decay job, add preference recalculation job |
| `tests/test_knowledge.py` | Create | Tests for knowledge module |
| `tests/test_preference_engine.py` | Create | Tests for preference engine |

---

### Task 1: Add Schema for Knowledge and Engagement Tables

**Files:**
- Modify: `memory/store.py`

- [ ] **Step 1: Write test for new tables**

Create `tests/__init__.py` and `tests/test_schema.py`:

```python
# tests/__init__.py
# empty

# tests/test_schema.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/civax/projects/ai_news_agent && python -m pytest tests/test_schema.py -v`
Expected: FAIL — tables don't exist

- [ ] **Step 3: Add tables to SCHEMA in store.py**

In `memory/store.py`, append to the `SCHEMA` string (after the existing `CREATE INDEX` statements):

```sql
CREATE TABLE IF NOT EXISTS knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT DEFAULT '',
    importance REAL DEFAULT 1.0,
    access_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    last_accessed TEXT NOT NULL,
    expires_at TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS engagement_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER,
    signal_type TEXT NOT NULL,
    topic TEXT DEFAULT '',
    source_name TEXT DEFAULT '',
    category TEXT DEFAULT '',
    weight REAL DEFAULT 1.0,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topic_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL UNIQUE,
    score REAL DEFAULT 0.0,
    sample_count INTEGER DEFAULT 0,
    last_updated TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL UNIQUE,
    score REAL DEFAULT 0.0,
    hit_count INTEGER DEFAULT 0,
    miss_count INTEGER DEFAULT 0,
    last_updated TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge(category);
CREATE INDEX IF NOT EXISTS idx_knowledge_importance ON knowledge(importance DESC);
CREATE INDEX IF NOT EXISTS idx_engagement_signals_type ON engagement_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_engagement_signals_topic ON engagement_signals(topic);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_schema.py -v`
Expected: All 4 PASS

- [ ] **Step 5: Add CRUD methods for knowledge table to Database class**

In `memory/store.py`, add these methods to the `Database` class:

```python
# --- Knowledge ---

async def insert_knowledge(self, category: str, content: str, source: str = "") -> int:
    now = datetime.now(timezone.utc).isoformat()
    cursor = await self.db.execute(
        """INSERT INTO knowledge (category, content, source, importance, access_count, created_at, last_accessed)
           VALUES (?, ?, ?, 1.0, 0, ?, ?)""",
        (category, content, source, now, now),
    )
    await self.db.commit()
    return cursor.lastrowid

async def get_top_knowledge(self, limit: int = 20) -> list[dict]:
    cursor = await self.db.execute(
        "SELECT * FROM knowledge WHERE importance >= 0.3 ORDER BY importance DESC, last_accessed DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]

async def touch_knowledge(self, knowledge_id: int):
    now = datetime.now(timezone.utc).isoformat()
    await self.db.execute(
        "UPDATE knowledge SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
        (now, knowledge_id),
    )
    await self.db.commit()

async def decay_knowledge(self, inactive_days: int = 7):
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=inactive_days)).isoformat()
    await self.db.execute(
        "UPDATE knowledge SET importance = importance * 0.95 WHERE last_accessed < ?",
        (cutoff,),
    )
    await self.db.execute(
        "DELETE FROM knowledge WHERE importance < 0.3 AND access_count < 2",
    )
    await self.db.commit()
```

- [ ] **Step 6: Add CRUD methods for engagement/scoring tables to Database class**

In `memory/store.py`, add:

```python
# --- Engagement Signals ---

async def add_engagement_signal(
    self, signal_type: str, topic: str = "", source_name: str = "",
    category: str = "", weight: float = 1.0, article_id: int | None = None,
):
    now = datetime.now(timezone.utc).isoformat()
    await self.db.execute(
        """INSERT INTO engagement_signals (article_id, signal_type, topic, source_name, category, weight, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (article_id, signal_type, topic, source_name, category, weight, now),
    )
    await self.db.commit()

async def get_topic_scores(self) -> dict[str, float]:
    cursor = await self.db.execute("SELECT topic, score FROM topic_scores ORDER BY ABS(score) DESC")
    rows = await cursor.fetchall()
    return {row["topic"]: row["score"] for row in rows}

async def update_topic_score(self, topic: str, delta: float):
    now = datetime.now(timezone.utc).isoformat()
    await self.db.execute(
        """INSERT INTO topic_scores (topic, score, sample_count, last_updated) VALUES (?, ?, 1, ?)
           ON CONFLICT(topic) DO UPDATE SET score = score * 0.9 + ? * 0.1, sample_count = sample_count + 1, last_updated = ?""",
        (topic, delta, now, delta, now),
    )
    await self.db.commit()

async def get_source_scores(self) -> dict[str, dict]:
    cursor = await self.db.execute("SELECT source_name, score, hit_count, miss_count FROM source_scores")
    rows = await cursor.fetchall()
    return {row["source_name"]: dict(row) for row in rows}

async def update_source_score(self, source_name: str, hit: bool):
    now = datetime.now(timezone.utc).isoformat()
    if hit:
        await self.db.execute(
            """INSERT INTO source_scores (source_name, score, hit_count, miss_count, last_updated) VALUES (?, 1.0, 1, 0, ?)
               ON CONFLICT(source_name) DO UPDATE SET score = score * 0.9 + 1.0 * 0.1, hit_count = hit_count + 1, last_updated = ?""",
            (source_name, now, now),
        )
    else:
        await self.db.execute(
            """INSERT INTO source_scores (source_name, score, hit_count, miss_count, last_updated) VALUES (?, -1.0, 0, 1, ?)
               ON CONFLICT(source_name) DO UPDATE SET score = score * 0.9 + (-1.0) * 0.1, miss_count = miss_count + 1, last_updated = ?""",
            (source_name, now, now),
        )
    await self.db.commit()
```

- [ ] **Step 7: Commit**

```bash
git add memory/store.py tests/
git commit -m "feat: add knowledge and engagement tables to schema with CRUD methods"
```

---

### Task 2: Knowledge Extraction Module

**Files:**
- Create: `memory/knowledge.py`
- Create: `tests/test_knowledge.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_knowledge.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_knowledge.py -v`
Expected: FAIL — `memory.knowledge` doesn't exist

- [ ] **Step 3: Implement KnowledgeManager**

Create `memory/knowledge.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_knowledge.py -v`
Expected: All 3 PASS

- [ ] **Step 5: Commit**

```bash
git add memory/knowledge.py tests/test_knowledge.py
git commit -m "feat: add KnowledgeManager for persistent memory extraction"
```

---

### Task 3: Preference Engine Module

**Files:**
- Create: `memory/preference_engine.py`
- Create: `tests/test_preference_engine.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_preference_engine.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_preference_engine.py -v`
Expected: FAIL — `memory.preference_engine` doesn't exist

- [ ] **Step 3: Implement PreferenceEngine**

Create `memory/preference_engine.py`:

```python
"""Multi-signal preference learning engine."""

import logging
from memory.store import Database

logger = logging.getLogger(__name__)

SIGNAL_WEIGHTS = {
    "deep_dive": 3.0,
    "feedback_positive": 2.0,
    "follow_up_question": 1.5,
    "conversation_mention": 1.0,
    "tip_submitted": 1.5,
    "no_reaction": -0.2,
    "feedback_negative": -2.0,
    "explicit_mute": -5.0,
}


class PreferenceEngine:
    def __init__(self, db: Database):
        self.db = db

    async def record_signal(
        self,
        signal_type: str,
        topic: str = "",
        source_name: str = "",
        category: str = "",
        article_id: int | None = None,
    ):
        """Record an engagement signal and update topic/source scores."""
        weight = SIGNAL_WEIGHTS.get(signal_type, 0.0)
        if weight == 0.0:
            return

        await self.db.add_engagement_signal(
            signal_type=signal_type,
            topic=topic,
            source_name=source_name,
            category=category,
            weight=weight,
            article_id=article_id,
        )

        # Update topic score
        if topic:
            await self.db.update_topic_score(topic, weight)

        # Update source score
        if source_name:
            is_positive = weight > 0
            await self.db.update_source_score(source_name, hit=is_positive)

    async def format_for_scoring(self) -> str:
        """Format preference data for injection into digest scoring prompt."""
        topics = await self.db.get_topic_scores()
        sources = await self.db.get_source_scores()

        lines = []
        if topics:
            boosted = [f"{t} ({s:+.1f})" for t, s in topics.items() if s > 0]
            muted = [f"{t} ({s:+.1f})" for t, s in topics.items() if s < 0]
            if boosted:
                lines.append(f"Boosted topics: {', '.join(boosted[:10])}")
            if muted:
                lines.append(f"Muted topics: {', '.join(muted[:10])}")

        if sources:
            good = [f"{s['source_name']} (hits:{s['hit_count']})" for s in sources.values() if s["score"] > 0]
            bad = [f"{s['source_name']} (misses:{s['miss_count']})" for s in sources.values() if s["score"] < 0]
            if good:
                lines.append(f"Preferred sources: {', '.join(good[:10])}")
            if bad:
                lines.append(f"Deprioritized sources: {', '.join(bad[:10])}")

        return "\n".join(lines) if lines else ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_preference_engine.py -v`
Expected: All 3 PASS

- [ ] **Step 5: Commit**

```bash
git add memory/preference_engine.py tests/test_preference_engine.py
git commit -m "feat: add PreferenceEngine for multi-signal preference learning"
```

---

### Task 4: Integrate Knowledge into Agent Core

**Files:**
- Modify: `agent/core.py`
- Modify: `agent/prompts.py`

- [ ] **Step 1: Update build_system_prompt to accept knowledge text**

In `agent/prompts.py`, modify `build_system_prompt`:

```python
def build_system_prompt(profile_summary: str, preference_summary: str = "", knowledge_summary: str = "") -> str:
    return f"""You are an autonomous AI news agent...

## Your User
{profile_summary}

... (existing prompt content) ...

{f"## Learned Preferences{chr(10)}{preference_summary}" if preference_summary else ""}

{f"## What You Know About This User{chr(10)}{knowledge_summary}" if knowledge_summary else ""}

## Output Style
...
"""
```

- [ ] **Step 2: Initialize KnowledgeManager and PreferenceEngine in AgentCore.__init__**

In `agent/core.py`, add to `__init__`:

```python
from memory.knowledge import KnowledgeManager
from memory.preference_engine import PreferenceEngine

# In __init__, after self.conversation = ConversationMemory(db):
self.knowledge = KnowledgeManager(db)
self.preferences = PreferenceEngine(db)
```

- [ ] **Step 3: Update _build_system to include knowledge**

In `agent/core.py`, modify `_build_system`:

```python
async def _build_system(self) -> str:
    pref_summary = await self._get_preference_summary()
    knowledge_summary = await self.knowledge.format_for_prompt()
    preference_scores = await self.preferences.format_for_scoring()
    combined_prefs = "\n".join(filter(None, [pref_summary, preference_scores]))
    return build_system_prompt(self.profile.get_profile_summary(), combined_prefs, knowledge_summary)
```

- [ ] **Step 4: Add knowledge extraction after conversations**

In `agent/core.py`, modify `handle_message` — add extraction after the response:

```python
async def handle_message(self, user_message: str) -> str:
    await self.conversation.add("user", user_message)
    history = await self.conversation.get_context()
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    response = await self._run_agent_loop(messages)
    await self.conversation.add("assistant", response)

    # Extract knowledge from this exchange (non-blocking best-effort)
    try:
        convo_text = f"User: {user_message}\nAssistant: {response}"
        extraction_prompt = self.knowledge.get_extraction_prompt(convo_text)
        extract_messages = [{"role": "user", "content": extraction_prompt}]
        extract_response = await self.llm.chat(messages=extract_messages, system="Extract knowledge items. Return JSON array only.")
        import json
        items = json.loads(self._extract_json(extract_response.content))
        if isinstance(items, list) and items:
            await self.knowledge.store_items(items)
            logger.info(f"Extracted {len(items)} knowledge items from conversation")
    except Exception as e:
        logger.debug(f"Knowledge extraction skipped: {e}")

    return response
```

- [ ] **Step 5: Commit**

```bash
git add agent/core.py agent/prompts.py
git commit -m "feat: integrate knowledge memory and preference engine into agent core"
```

---

### Task 5: Record Engagement Signals from All Interactions

**Files:**
- Modify: `delivery/bot.py`
- Modify: `agent/core.py`

- [ ] **Step 1: Record feedback signals with topics**

In `delivery/bot.py`, modify `_handle_callback` — after `await self.db.add_feedback(article_id, action)`, add preference engine signal:

```python
if action in ("relevant", "not_for_me"):
    await self.db.add_feedback(article_id, action)
    # Record engagement signal with topic extraction
    article = await self.db.get_article_by_id(article_id)
    if article:
        signal_type = "feedback_positive" if action == "relevant" else "feedback_negative"
        await self.agent.preferences.record_signal(
            signal_type=signal_type,
            topic=article.get("category", ""),
            source_name=article.get("source_name", ""),
            category=article.get("category", ""),
            article_id=article_id,
        )
    emoji = "noted" if action == "relevant" else "noted, less of this"
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text=f"Feedback: {emoji}")
elif action == "deep_dive":
    # Record deep dive as strong positive signal
    article = await self.db.get_article_by_id(article_id)
    if article:
        await self.agent.preferences.record_signal(
            signal_type="deep_dive",
            topic=article.get("category", ""),
            source_name=article.get("source_name", ""),
            category=article.get("category", ""),
            article_id=article_id,
        )
    await context.bot.send_message(chat_id=query.message.chat_id, text="Fetching deep dive...")
    result = await self.agent.deep_dive(article_id)
    await self._send_long_message(query.message.chat_id, result)
```

- [ ] **Step 2: Record tip_submitted signal in investigate_tip**

In `agent/core.py`, in `investigate_tip`, after storing the article, add:

```python
await self.preferences.record_signal(
    signal_type="tip_submitted",
    topic="user_tip",
    source_name="User Tip",
)
```

- [ ] **Step 3: Commit**

```bash
git add delivery/bot.py agent/core.py
git commit -m "feat: record engagement signals from feedback, deep dives, and tips"
```

---

### Task 6: Add Scheduled Knowledge Decay and Preference Recalculation

**Files:**
- Modify: `tasks/scheduler.py`

- [ ] **Step 1: Add knowledge decay job**

In `tasks/scheduler.py`, in `start()`, add after the preference update job:

```python
# Knowledge decay - daily at 4am
self.scheduler.add_job(
    self._knowledge_decay,
    CronTrigger(hour=4, minute=0),
    id="knowledge_decay",
    name="Knowledge decay",
    misfire_grace_time=600,
)
```

- [ ] **Step 2: Add the decay method**

In `tasks/scheduler.py`, add:

```python
async def _knowledge_decay(self):
    try:
        await self.db.decay_knowledge(inactive_days=7)
        logger.info("Knowledge decay complete")
    except Exception as e:
        logger.error(f"Knowledge decay failed: {e}")
```

- [ ] **Step 3: Commit**

```bash
git add tasks/scheduler.py
git commit -m "feat: add scheduled knowledge decay job"
```

---

### Task 7: Add /knowledge Telegram Command

**Files:**
- Modify: `delivery/bot.py`

- [ ] **Step 1: Register the command handler**

In `delivery/bot.py`, in `start()`, add after the other command handlers:

```python
self._app.add_handler(CommandHandler("knowledge", self._cmd_knowledge))
```

- [ ] **Step 2: Implement the command**

In `delivery/bot.py`, add the method:

```python
async def _cmd_knowledge(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not self._is_authorized(update):
        return
    from memory.knowledge import KnowledgeManager
    km = KnowledgeManager(self.db)
    items = await km.get_relevant(limit=20)
    if items:
        text = "What I know about you:\n\n"
        for item in items:
            imp = f"{item['importance']:.1f}"
            text += f"[{item['category']}] {item['content']} (importance: {imp})\n"
    else:
        text = "No knowledge stored yet. Chat with me to build up my understanding of you."
    await self._send_long_message(update.effective_chat.id, text)
```

- [ ] **Step 3: Update help text**

In `_cmd_help`, add: `"/knowledge - show what the agent remembers about you\n"`

- [ ] **Step 4: Commit**

```bash
git add delivery/bot.py
git commit -m "feat: add /knowledge command to view agent's persistent memory"
```

---

### Task 8: Include Preference Scores in Digest Scoring

**Files:**
- Modify: `agent/prompts.py`
- Modify: `agent/core.py`

- [ ] **Step 1: Update DIGEST_TASK_PROMPT to include preference data**

In `agent/prompts.py`, update `DIGEST_TASK_PROMPT` — add after the "CRITICAL: Only include articles from the LAST 48 HOURS" line:

```python
DIGEST_TASK_PROMPT = """Review the following collected articles and produce a curated digest.

CRITICAL: Only include articles from the LAST 48 HOURS. ...existing instructions...

Preference data from user's history:
{preferences}

Use these preferences to adjust your scoring — boost topics and sources the user engages with, deprioritize those they consistently reject.

Articles to review:
{articles}

...rest of prompt...
"""
```

- [ ] **Step 2: Pass preference data into compile_digest**

In `agent/core.py`, in `compile_digest`, before building the prompt:

```python
preference_text = await self.preferences.format_for_scoring()
prompt = DIGEST_TASK_PROMPT.format(articles=article_text, preferences=preference_text or "No preference data yet.")
```

- [ ] **Step 3: Commit**

```bash
git add agent/prompts.py agent/core.py
git commit -m "feat: include learned preferences in digest scoring prompt"
```

---

### Task 9: Run All Tests and Final Verification

- [ ] **Step 1: Install pytest if needed**

```bash
pip install --break-system-packages pytest
```

- [ ] **Step 2: Run all tests**

```bash
cd /home/civax/projects/ai_news_agent && python -m pytest tests/ -v
```

Expected: All tests pass

- [ ] **Step 3: Manual integration test**

```bash
python -c "
import asyncio
from config import settings
from memory.store import Database
from memory.knowledge import KnowledgeManager
from memory.preference_engine import PreferenceEngine

async def test():
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = Database(settings.DB_PATH)
    await db.initialize()
    
    km = KnowledgeManager(db)
    await km.store_items([{'category': 'user_fact', 'content': 'Test knowledge item'}])
    print('Knowledge:', await km.format_for_prompt())
    
    pe = PreferenceEngine(db)
    await pe.record_signal('feedback_positive', topic='Godot', source_name='r/godot')
    await pe.record_signal('feedback_negative', topic='crypto', source_name='HN')
    print('Preferences:', await pe.format_for_scoring())
    
    await db.close()

asyncio.run(test())
"
```

Expected: Both print meaningful output

- [ ] **Step 4: Start agent and verify it runs**

```bash
python main.py
```

Expected: Agent starts without errors, scheduled jobs register

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete knowledge memory and preference engine (evolution phases 1+2)"
git push origin master
```
