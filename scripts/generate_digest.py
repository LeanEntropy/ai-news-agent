"""Generate a digest locally without sending it to Telegram.

Archives the digest to the database so it shows up at /digests in the web UI.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from memory.store import Database
from memory.user_profile import UserProfile
from llm.factory import create_llm_provider
from agent.core import AgentCore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

    db = Database(settings.DB_PATH)
    await db.initialize()

    try:
        llm = create_llm_provider()
        profile = UserProfile.load()
        agent = AgentCore(llm=llm, db=db, profile=profile)

        logger.info("Compiling digest (bypassing cooldown)...")
        digest_items = await agent.compile_digest(force=True)

        if not digest_items:
            logger.warning("No articles available for digest.")
            return

        # Archive it for the web repository
        article_ids = [i["article_id"] for i in digest_items if "article_id" in i]
        if article_ids:
            digest_id = await db.insert_digest_archive("local", article_ids)
            logger.info(f"Archived digest #{digest_id} with {len(article_ids)} items")
            print()
            print(f"Digest generated with {len(article_ids)} items.")
            print(f"View at: http://localhost:8080/digests/{digest_id}")
            print(f"Archive:  http://localhost:8080/digests")
            print()

        # Also print a compact summary to stdout
        print("=" * 60)
        print("DIGEST SUMMARY")
        print("=" * 60)
        by_cat: dict[str, list[dict]] = {}
        for item in digest_items:
            cat = (item.get("category") or "general_ai").upper()
            by_cat.setdefault(cat, []).append(item)
        for cat, items in by_cat.items():
            print(f"\n[{cat}]")
            for i in items:
                title = i.get("title") or "(no title)"
                src = i.get("source_name") or ""
                score = (i.get("importance_score", 0) + i.get("relevance_score", 0)) / 2
                print(f"  - {title} ({src}) score~{score:.1f}")
                summary = i.get("summary", "")
                if summary:
                    print(f"    {summary}")
                url = i.get("url", "")
                if url:
                    print(f"    {url}")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
