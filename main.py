import asyncio
import logging
import signal

from config import settings
from memory.store import Database
from tasks.scheduler import Scheduler
from telegram.bot import TelegramBot
from agent.core import AgentCore
from llm.factory import create_llm_provider
from memory.user_profile import UserProfile

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    # Ensure data directory exists
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize components
    db = Database(settings.DB_PATH)
    await db.initialize()

    llm = create_llm_provider()
    profile = UserProfile.load()
    agent = AgentCore(llm=llm, db=db, profile=profile)
    bot = TelegramBot(agent=agent, db=db)
    scheduler = Scheduler(agent=agent, bot=bot, db=db)

    # Graceful shutdown
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def handle_signal():
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    logger.info("Starting AI News Agent...")

    # Start bot and scheduler
    await bot.start()
    scheduler.start()

    logger.info("Agent is running. Press Ctrl+C to stop.")
    await stop_event.wait()

    # Cleanup
    logger.info("Shutting down...")
    scheduler.stop()
    await bot.stop()
    await db.close()
    logger.info("Goodbye.")


if __name__ == "__main__":
    asyncio.run(main())
