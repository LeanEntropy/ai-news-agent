"""Telegram bot - conversational interface and digest delivery."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import settings
from memory.store import Database
from delivery.formatter import format_digest, format_discovery, format_stats

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, agent, db: Database):
        self.agent = agent
        self.db = db
        self._app: Application | None = None

    async def start(self):
        if not settings.TELEGRAM_BOT_TOKEN:
            logger.warning("No TELEGRAM_BOT_TOKEN set, Telegram bot disabled")
            return

        builder = Application.builder().token(settings.TELEGRAM_BOT_TOKEN)
        self._app = builder.build()

        # Register handlers
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("digest", self._cmd_digest))
        self._app.add_handler(CommandHandler("search", self._cmd_search))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("preferences", self._cmd_preferences))
        self._app.add_handler(CommandHandler("review", self._cmd_review))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(CallbackQueryHandler(self._handle_callback))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot started")

    async def stop(self):
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    def _is_authorized(self, update: Update) -> bool:
        """Check if the message is from the authorized user."""
        if not settings.TELEGRAM_CHAT_ID:
            return True  # No restriction if not configured
        return str(update.effective_chat.id) == str(settings.TELEGRAM_CHAT_ID)

    # --- Commands ---

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        await update.message.reply_text(
            "AI News Agent is active.\n\n"
            "I'll send you digests twice daily. You can also:\n"
            "- Send me any message to chat\n"
            "- /digest - get a digest now\n"
            "- /search <query> - search for repos or news\n"
            "- /status - see agent stats\n"
            "- /preferences - view learned preferences\n"
            "- /help - show commands"
        )

    async def _cmd_digest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        digest_items = await self.agent.compile_digest()
        if digest_items and len(digest_items) == 1 and digest_items[0].get("_cooldown"):
            mins = digest_items[0].get("_remaining_minutes", 0)
            await update.message.reply_text(f"Cooldown active. Next digest available in ~{mins} minutes.")
            return
        await update.message.reply_text("Compiling digest...")
        if digest_items:
            await self._send_digest_messages(update.effective_chat.id, digest_items, "on-demand")
        else:
            await update.message.reply_text("No new articles to digest right now.")

    async def _cmd_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        query = " ".join(context.args) if context.args else ""
        if not query:
            await update.message.reply_text("Usage: /search <query>\nExample: /search MCP server for Unity")
            return
        await update.message.reply_text(f"Searching: {query}...")
        result = await self.agent.search_on_demand(query)
        await self._send_long_message(update.effective_chat.id, result)

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        stats = await self.db.get_stats()
        await update.message.reply_text(format_stats(stats), parse_mode="HTML")

    async def _cmd_preferences(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        prefs = await self.db.get_preference("learned_weights")
        if prefs:
            text = "Learned preferences:\n"
            if "category_weights" in prefs:
                text += f"\nCategory weights: {prefs['category_weights']}"
            if "boosted_topics" in prefs:
                text += f"\nBoosted: {', '.join(prefs['boosted_topics'])}"
            if "muted_topics" in prefs:
                text += f"\nMuted: {', '.join(prefs['muted_topics'])}"
            if "notes" in prefs:
                text += f"\nAnalysis: {prefs['notes']}"
        else:
            text = "No preferences learned yet. React to digest items to teach me your preferences."
        await update.message.reply_text(text)

    async def _cmd_review(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        webapp_url = settings.WEBAPP_URL
        if not webapp_url:
            await update.message.reply_text("Review page not configured. Set WEBAPP_URL in .env")
            return
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Open Review Page", web_app=WebAppInfo(url=webapp_url))]
        ])
        await update.message.reply_text(
            "Review and rate articles, bookmark items for later:",
            reply_markup=keyboard,
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        await update.message.reply_text(
            "Commands:\n"
            "/digest - compile and send a digest now\n"
            "/search <query> - search for repos, tools, or news\n"
            "/review - open the web review page\n"
            "/status - agent statistics\n"
            "/preferences - view learned preferences\n"
            "/help - this message\n\n"
            "Send a URL and I'll investigate it for you.\n"
            "Or just send any message to chat."
        )

    # --- Message handling ---

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        user_message = update.message.text

        # Detect if message contains a URL - treat as a tip to investigate
        import re
        urls = re.findall(r'https?://\S+', user_message)
        if urls:
            await update.message.reply_text("Looking into that...")
            response = await self.agent.investigate_tip(user_message, urls)
        else:
            response = await self.agent.handle_message(user_message)

        await self._send_long_message(update.effective_chat.id, response)

    # --- Callback handling (feedback buttons) ---

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        data = query.data
        if not data:
            return

        parts = data.split(":")
        if len(parts) != 2:
            return

        action, article_id_str = parts
        try:
            article_id = int(article_id_str)
        except ValueError:
            return

        if action in ("relevant", "not_for_me"):
            await self.db.add_feedback(article_id, action)
            emoji = "noted" if action == "relevant" else "noted, less of this"
            await query.edit_message_reply_markup(reply_markup=None)
            # Send a brief acknowledgment
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"Feedback: {emoji}",
            )
        elif action == "deep_dive":
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Fetching deep dive...",
            )
            result = await self.agent.deep_dive(article_id)
            await self._send_long_message(query.message.chat_id, result)

    # --- Digest delivery ---

    async def send_digest(self, digest_items: list[dict], period: str = "morning"):
        """Send a digest to the configured chat."""
        if not self._app or not settings.TELEGRAM_CHAT_ID:
            return
        await self._send_digest_messages(
            int(settings.TELEGRAM_CHAT_ID), digest_items, period
        )

    async def _send_digest_messages(
        self, chat_id: int, items: list[dict], period: str
    ):
        """Format and send digest with feedback buttons."""
        messages = format_digest(items, period)

        for msg in messages:
            try:
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            except Exception as e:
                logger.warning(f"HTML send failed: {e}")
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=msg.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""),
                    disable_web_page_preview=True,
                )

        # Send individual items with feedback buttons
        for item in items:
            article_id = item.get("article_id")
            if not article_id:
                continue
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Relevant", callback_data=f"relevant:{article_id}"),
                    InlineKeyboardButton("Not for me", callback_data=f"not_for_me:{article_id}"),
                    InlineKeyboardButton("Deep dive", callback_data=f"deep_dive:{article_id}"),
                ]
            ])
            title = item.get("title", item.get("summary", "")[:60])
            try:
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=f"{title}",
                    reply_markup=keyboard,
                )
            except Exception as e:
                logger.warning(f"Failed to send feedback buttons for article {article_id}: {e}")

        # Mark as delivered
        article_ids = [i["article_id"] for i in items if "article_id" in i]
        await self.db.mark_articles_delivered(article_ids)

    async def _send_long_message(self, chat_id: int, text: str):
        """Send a message, splitting if too long."""
        if not self._app:
            return
        chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
        for chunk in chunks:
            await self._app.bot.send_message(
                chat_id=chat_id,
                text=chunk,
                disable_web_page_preview=True,
            )
