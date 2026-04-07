import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    category TEXT DEFAULT 'general_ai',
    importance_score REAL DEFAULT 0.0,
    relevance_score REAL DEFAULT 0.0,
    final_score REAL DEFAULT 0.0,
    source_name TEXT DEFAULT '',
    source_type TEXT DEFAULT '',
    published_at TEXT DEFAULT '',
    collected_at TEXT NOT NULL,
    delivered INTEGER DEFAULT 0,
    url_hash TEXT NOT NULL,
    UNIQUE(url_hash)
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    reaction TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (article_id) REFERENCES articles(id)
);

CREATE TABLE IF NOT EXISTS preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discoveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    reasoning TEXT DEFAULT '',
    project_name TEXT DEFAULT '',
    discovered_at TEXT NOT NULL,
    delivered INTEGER DEFAULT 0,
    UNIQUE(url)
);

CREATE INDEX IF NOT EXISTS idx_articles_collected ON articles(collected_at);
CREATE INDEX IF NOT EXISTS idx_articles_delivered ON articles(delivered);
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
CREATE INDEX IF NOT EXISTS idx_articles_score ON articles(final_score DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_article ON feedback(article_id);
"""


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        logger.info(f"Database initialized at {self.db_path}")

    async def close(self):
        if self._db:
            await self._db.close()

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "Database not initialized"
        return self._db

    # --- Articles ---

    async def insert_article(
        self,
        url: str,
        title: str,
        content: str = "",
        source_name: str = "",
        source_type: str = "",
        published_at: str = "",
    ) -> int | None:
        """Insert an article. Returns ID if new, None if duplicate."""
        url_hash = _hash(url + title)
        now = datetime.now(timezone.utc).isoformat()
        try:
            cursor = await self.db.execute(
                """INSERT INTO articles (url, title, content, source_name, source_type,
                   published_at, collected_at, url_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (url, title, content, source_name, source_type, published_at, now, url_hash),
            )
            await self.db.commit()
            return cursor.lastrowid
        except aiosqlite.IntegrityError:
            return None  # Duplicate

    async def get_undelivered_articles(self, since: str = "") -> list[dict]:
        """Get articles not yet delivered, optionally since a timestamp."""
        if since:
            cursor = await self.db.execute(
                "SELECT * FROM articles WHERE delivered = 0 AND collected_at >= ? ORDER BY final_score DESC",
                (since,),
            )
        else:
            cursor = await self.db.execute(
                "SELECT * FROM articles WHERE delivered = 0 ORDER BY final_score DESC"
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_unscored_articles(self) -> list[dict]:
        """Get articles that haven't been scored yet."""
        cursor = await self.db.execute(
            "SELECT * FROM articles WHERE final_score = 0.0 ORDER BY collected_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def update_article_scores(
        self,
        article_id: int,
        category: str,
        importance_score: float,
        relevance_score: float,
        final_score: float,
        summary: str,
    ):
        await self.db.execute(
            """UPDATE articles SET category = ?, importance_score = ?,
               relevance_score = ?, final_score = ?, summary = ?
               WHERE id = ?""",
            (category, importance_score, relevance_score, final_score, summary, article_id),
        )
        await self.db.commit()

    async def mark_articles_delivered(self, article_ids: list[int]):
        if not article_ids:
            return
        placeholders = ",".join("?" * len(article_ids))
        await self.db.execute(
            f"UPDATE articles SET delivered = 1 WHERE id IN ({placeholders})",
            article_ids,
        )
        await self.db.commit()

    async def get_article_by_id(self, article_id: int) -> dict | None:
        cursor = await self.db.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    # --- Feedback ---

    async def add_feedback(self, article_id: int, reaction: str):
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "INSERT INTO feedback (article_id, reaction, timestamp) VALUES (?, ?, ?)",
            (article_id, reaction, now),
        )
        await self.db.commit()

    async def get_all_feedback(self) -> list[dict]:
        cursor = await self.db.execute(
            """SELECT f.*, a.category, a.source_name, a.title
               FROM feedback f JOIN articles a ON f.article_id = a.id
               ORDER BY f.timestamp DESC"""
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_feedback_count(self) -> int:
        cursor = await self.db.execute("SELECT COUNT(*) FROM feedback")
        row = await cursor.fetchone()
        return row[0] if row else 0

    # --- Preferences ---

    async def get_preference(self, key: str) -> dict | None:
        cursor = await self.db.execute(
            "SELECT value FROM preferences WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return json.loads(row[0]) if row else None

    async def set_preference(self, key: str, value: dict):
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """INSERT INTO preferences (key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?""",
            (key, json.dumps(value), now, json.dumps(value), now),
        )
        await self.db.commit()

    # --- Conversations ---

    async def add_conversation_message(self, role: str, content: str):
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "INSERT INTO conversations (role, content, timestamp) VALUES (?, ?, ?)",
            (role, content, now),
        )
        await self.db.commit()

    async def get_recent_conversations(self, limit: int = 20) -> list[dict]:
        cursor = await self.db.execute(
            "SELECT role, content FROM conversations ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in reversed(rows)]

    # --- Discoveries ---

    async def insert_discovery(
        self, url: str, title: str, description: str, reasoning: str, project_name: str = ""
    ) -> int | None:
        now = datetime.now(timezone.utc).isoformat()
        try:
            cursor = await self.db.execute(
                """INSERT INTO discoveries (url, title, description, reasoning, project_name, discovered_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (url, title, description, reasoning, project_name, now),
            )
            await self.db.commit()
            return cursor.lastrowid
        except aiosqlite.IntegrityError:
            return None

    async def get_undelivered_discoveries(self) -> list[dict]:
        cursor = await self.db.execute(
            "SELECT * FROM discoveries WHERE delivered = 0 ORDER BY discovered_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def mark_discoveries_delivered(self, ids: list[int]):
        if not ids:
            return
        placeholders = ",".join("?" * len(ids))
        await self.db.execute(
            f"UPDATE discoveries SET delivered = 1 WHERE id IN ({placeholders})", ids
        )
        await self.db.commit()

    # --- Stats ---

    async def get_stats(self) -> dict:
        articles = await self.db.execute("SELECT COUNT(*) FROM articles")
        delivered = await self.db.execute("SELECT COUNT(*) FROM articles WHERE delivered = 1")
        feedback = await self.db.execute("SELECT COUNT(*) FROM feedback")
        discoveries = await self.db.execute("SELECT COUNT(*) FROM discoveries")
        return {
            "total_articles": (await articles.fetchone())[0],
            "delivered_articles": (await delivered.fetchone())[0],
            "total_feedback": (await feedback.fetchone())[0],
            "total_discoveries": (await discoveries.fetchone())[0],
        }


def _hash(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()[:32]
