"""Task scheduler - runs periodic agent tasks."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import settings

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, agent, bot, db):
        self.agent = agent
        self.bot = bot
        self.db = db
        self.scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)

    def start(self):
        # Source collection - every N hours
        self.scheduler.add_job(
            self._source_scan,
            IntervalTrigger(hours=settings.SOURCE_SCAN_INTERVAL_HOURS),
            id="source_scan",
            name="Source scan",
            misfire_grace_time=300,
        )

        # Proactive discovery - every N hours
        self.scheduler.add_job(
            self._discovery,
            IntervalTrigger(hours=settings.DISCOVERY_INTERVAL_HOURS),
            id="discovery",
            name="Proactive discovery",
            misfire_grace_time=300,
        )

        # Morning digest
        self.scheduler.add_job(
            self._digest,
            CronTrigger(
                hour=settings.MORNING_DIGEST_HOUR,
                minute=settings.MORNING_DIGEST_MINUTE,
            ),
            id="morning_digest",
            name="Morning digest",
            kwargs={"period": "morning"},
            misfire_grace_time=600,
        )

        # Evening digest
        self.scheduler.add_job(
            self._digest,
            CronTrigger(
                hour=settings.EVENING_DIGEST_HOUR,
                minute=settings.EVENING_DIGEST_MINUTE,
            ),
            id="evening_digest",
            name="Evening digest",
            kwargs={"period": "evening"},
            misfire_grace_time=600,
        )

        # Preference update - daily at 3am
        self.scheduler.add_job(
            self._update_preferences,
            CronTrigger(hour=3, minute=0),
            id="preference_update",
            name="Preference update",
            misfire_grace_time=600,
        )

        # Knowledge decay - daily at 4am
        self.scheduler.add_job(
            self._knowledge_decay,
            CronTrigger(hour=4, minute=0),
            id="knowledge_decay",
            name="Knowledge decay",
            misfire_grace_time=600,
        )

        # Run initial source scan on startup
        self.scheduler.add_job(
            self._source_scan,
            id="initial_scan",
            name="Initial source scan",
        )

        self.scheduler.start()
        logger.info("Scheduler started with all jobs")

    def stop(self):
        self.scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    async def _source_scan(self):
        try:
            count = await self.agent.collect_from_sources()
            logger.info(f"Source scan complete: {count} new articles")
        except Exception as e:
            logger.error(f"Source scan failed: {e}")

    async def _discovery(self):
        try:
            discoveries = await self.agent.discover_repos()
            logger.info(f"Discovery complete: {len(discoveries)} new finds")
        except Exception as e:
            logger.error(f"Discovery failed: {e}")

    async def _digest(self, period: str = "morning"):
        try:
            digest_items = await self.agent.compile_digest(force=True)
            if digest_items:
                await self.bot.send_digest(digest_items, period)
                logger.info(f"{period.title()} digest sent with {len(digest_items)} items")
            else:
                logger.info(f"No items for {period} digest")
        except Exception as e:
            logger.error(f"Digest failed: {e}")

    async def _knowledge_decay(self):
        try:
            await self.db.decay_knowledge(inactive_days=7)
            logger.info("Knowledge decay complete")
        except Exception as e:
            logger.error(f"Knowledge decay failed: {e}")

    async def _update_preferences(self):
        try:
            await self.agent.update_preferences()
            logger.info("Preference update complete")
        except Exception as e:
            logger.error(f"Preference update failed: {e}")
