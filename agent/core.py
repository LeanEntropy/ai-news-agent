"""Agent core - the reasoning brain."""

import json
import logging

import yaml

from agent.prompts import (
    DIGEST_TASK_PROMPT,
    DISCOVERY_TASK_PROMPT,
    PREFERENCE_UPDATE_PROMPT,
    build_system_prompt,
)
from agent.tools import TOOL_SCHEMAS, execute_tool
from config import settings
from llm.base import LLMProvider
from memory.conversation import ConversationMemory
from memory.knowledge import KnowledgeManager
from memory.preference_engine import PreferenceEngine
from memory.store import Database
from memory.user_profile import UserProfile

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10


class AgentCore:
    def __init__(self, llm: LLMProvider, db: Database, profile: UserProfile):
        self.llm = llm
        self.db = db
        self.profile = profile
        self.conversation = ConversationMemory(db)
        self.knowledge = KnowledgeManager(db)
        self.preferences = PreferenceEngine(db)
        self._sources_config = self._load_sources()

    def _load_sources(self) -> dict:
        """Load sources from user config, falling back to defaults."""
        user_sources = settings.USER_CONFIG_DIR / "sources.yaml"
        default_sources = settings.CONFIG_DIR / "default_sources.yaml"

        with open(default_sources) as f:
            config = yaml.safe_load(f) or {}

        if user_sources.exists():
            with open(user_sources) as f:
                user = yaml.safe_load(f) or {}
            # Merge user overrides
            for key in ("rss", "github", "reddit", "hackernews", "twitter"):
                if key in user:
                    if key == "rss" and "custom" in user["rss"]:
                        config.setdefault("rss", {})["custom"] = user["rss"]["custom"]
                    elif key == "twitter":
                        config["twitter"] = user["twitter"]
                    elif key == "github":
                        gh = config.setdefault("github", {})
                        gh.setdefault("search_queries", []).extend(
                            user.get("github", {}).get("extra_search_queries", [])
                        )
                        gh.setdefault("watch_orgs", []).extend(
                            user.get("github", {}).get("extra_watch_orgs", [])
                        )
                    elif key == "reddit":
                        config.setdefault("reddit", {}).setdefault("subreddits", []).extend(
                            user.get("reddit", {}).get("extra_subreddits", [])
                        )
        return config

    async def _get_preference_summary(self) -> str:
        """Get learned preferences as text for the system prompt."""
        prefs = await self.db.get_preference("learned_weights")
        if not prefs:
            return ""
        lines = []
        if "category_weights" in prefs:
            lines.append(f"Category weights: {prefs['category_weights']}")
        if "boosted_topics" in prefs:
            lines.append(f"Boosted topics: {', '.join(prefs['boosted_topics'])}")
        if "muted_topics" in prefs:
            lines.append(f"Muted topics: {', '.join(prefs['muted_topics'])}")
        if "notes" in prefs:
            lines.append(f"Analysis: {prefs['notes']}")
        return "\n".join(lines)

    async def _build_system(self) -> str:
        pref_summary = await self._get_preference_summary()
        knowledge_summary = await self.knowledge.format_for_prompt()
        preference_scores = await self.preferences.format_for_scoring()
        combined_prefs = "\n".join(filter(None, [pref_summary, preference_scores]))
        return build_system_prompt(self.profile.get_profile_summary(), combined_prefs, knowledge_summary)

    async def _run_agent_loop(
        self, messages: list[dict], system: str = "", use_tools: bool = True
    ) -> str:
        """Run the agent reasoning loop with tool use until done."""
        if not system:
            system = await self._build_system()

        tools = TOOL_SCHEMAS if use_tools else None

        for _ in range(MAX_TOOL_ROUNDS):
            response = await self.llm.chat(messages=messages, system=system, tools=tools)

            if not response.tool_calls:
                return response.content

            # Process tool calls
            # Add assistant message with tool calls
            messages.append({"role": "assistant", "content": response.content, "_tool_calls": response.tool_calls})

            for tc in response.tool_calls:
                logger.info(f"Calling tool: {tc.name}({json.dumps(tc.arguments)[:200]})")
                result = await execute_tool(tc.name, tc.arguments, self._sources_config)

                # Add tool result - format depends on provider
                messages.append({
                    "role": "user",
                    "content": f"[Tool result for {tc.name}]: {result[:8000]}",
                })

        return response.content if response else ""

    # --- Public task methods ---

    async def handle_message(self, user_message: str) -> str:
        """Handle a conversational message from the user."""
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
            items = json.loads(self._extract_json(extract_response.content))
            if isinstance(items, list) and items:
                await self.knowledge.store_items(items)
                logger.info(f"Extracted {len(items)} knowledge items from conversation")
        except Exception as e:
            logger.debug(f"Knowledge extraction skipped: {e}")

        return response

    async def compile_digest(self, force: bool = False) -> list[dict]:
        """Compile a news digest from collected articles.

        Args:
            force: If True, skip the cooldown check.
        """
        # Cooldown: minimum 2 hours between digests
        if not force:
            last = await self.db.get_preference("last_digest_time")
            if last:
                from datetime import datetime, timezone
                last_time = datetime.fromisoformat(last["time"])
                elapsed = (datetime.now(timezone.utc) - last_time).total_seconds()
                if elapsed < 7200:  # 2 hours
                    remaining = int((7200 - elapsed) / 60)
                    return [{"_cooldown": True, "_remaining_minutes": remaining}]

        articles = await self.db.get_unscored_articles()
        if not articles:
            articles = await self.db.get_undelivered_articles()
        if not articles:
            return []

        # Prepare articles for the LLM - include date for recency judgment
        from datetime import datetime as _dt, timezone as _tz
        now_str = _dt.now(_tz.utc).strftime("%Y-%m-%d %H:%M UTC")
        article_text = f"Current time: {now_str}\n\n"
        article_text += "\n".join(
            f"[ID:{a['id']}] [Published: {a.get('published_at', 'unknown')[:16]}] {a['title']} ({a['source_name']}) - {a['url']}\n{a['content'][:300]}"
            for a in articles[:50]
        )

        prompt = DIGEST_TASK_PROMPT.format(articles=article_text)
        messages = [{"role": "user", "content": prompt}]
        response = await self._run_agent_loop(messages, use_tools=False)

        # Parse response
        logger.info(f"Digest LLM response length: {len(response)}, first 500 chars: {response[:500]}")
        try:
            extracted = self._extract_json(response)
            data = json.loads(extracted)
            digest_items = data.get("digest", [])
            logger.info(f"Parsed {len(digest_items)} digest items")
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse digest response: {e}")
            logger.error(f"Raw response: {response[:1000]}")
            return []

        # Update scores in DB and enrich items with article data (url, title, source)
        enriched = []
        for item in digest_items:
            article_id = item.get("article_id")
            if article_id:
                importance = item.get("importance_score", 0)
                relevance = item.get("relevance_score", 0)
                cat = item.get("category", "general_ai").lower()
                weight = self.profile.categories.get(cat, type("", (), {"weight": 1.0})).weight
                final = (importance * 0.4 + relevance * 0.6) * weight

                await self.db.update_article_scores(
                    article_id=article_id,
                    category=cat,
                    importance_score=importance,
                    relevance_score=relevance,
                    final_score=final,
                    summary=item.get("summary", ""),
                )

                # Enrich with DB data
                article = await self.db.get_article_by_id(article_id)
                if article:
                    item["url"] = item.get("url") or article.get("url", "")
                    item["title"] = item.get("title") or article.get("title", "")
                    item["source_name"] = item.get("source_name") or article.get("source_name", "")

            enriched.append(item)

        # Record digest time for cooldown
        from datetime import datetime as _dt, timezone as _tz
        await self.db.set_preference("last_digest_time", {"time": _dt.now(_tz.utc).isoformat()})

        return enriched

    async def discover_repos(self) -> list[dict]:
        """Proactively search for repos relevant to user's projects."""
        messages = [{"role": "user", "content": DISCOVERY_TASK_PROMPT}]
        response = await self._run_agent_loop(messages)

        try:
            data = json.loads(self._extract_json(response))
            discoveries = data.get("discoveries", [])
        except (json.JSONDecodeError, KeyError):
            logger.error("Failed to parse discovery response")
            return []

        # Store discoveries
        for d in discoveries:
            await self.db.insert_discovery(
                url=d.get("url", ""),
                title=d.get("title", ""),
                description=d.get("description", ""),
                reasoning=d.get("reasoning", ""),
                project_name=d.get("project_name", ""),
            )

        return discoveries

    async def deep_dive(self, article_id: int) -> str:
        """Provide a detailed analysis of an article."""
        article = await self.db.get_article_by_id(article_id)
        if not article:
            return "Article not found."

        messages = [
            {
                "role": "user",
                "content": (
                    f"Provide a detailed analysis of this article:\n"
                    f"Title: {article['title']}\n"
                    f"URL: {article['url']}\n"
                    f"Summary: {article['summary']}\n\n"
                    f"Use the browse_url tool to read the full article, then provide:\n"
                    f"1. Key facts and developments\n"
                    f"2. Why this matters (to AI industry and to my projects)\n"
                    f"3. Related context or implications\n"
                    f"Keep it factual and concise."
                ),
            }
        ]
        return await self._run_agent_loop(messages)

    async def update_preferences(self):
        """Analyze feedback and update preference weights."""
        feedback = await self.db.get_all_feedback()
        if len(feedback) < 5:
            return  # Not enough data

        current = await self.db.get_preference("learned_weights") or {}

        prompt = PREFERENCE_UPDATE_PROMPT.format(
            feedback=json.dumps(feedback[:100], default=str),
            current_preferences=json.dumps(current, default=str),
        )
        messages = [{"role": "user", "content": prompt}]
        response = await self._run_agent_loop(messages, use_tools=False)

        try:
            new_prefs = json.loads(self._extract_json(response))
            await self.db.set_preference("learned_weights", new_prefs)
            logger.info(f"Updated preferences: {new_prefs.get('notes', '')}")
        except (json.JSONDecodeError, KeyError):
            logger.error("Failed to parse preference update response")

    async def investigate_tip(self, user_message: str, urls: list[str]) -> str:
        """User sent a link or tip. Browse it, summarize, store, and explain relevance."""
        await self.conversation.add("user", user_message)

        messages = [
            {
                "role": "user",
                "content": (
                    f"The user shared this tip: {user_message}\n\n"
                    f"URLs to investigate: {', '.join(urls)}\n\n"
                    f"Use the browse_url tool to read each URL. Then:\n"
                    f"1. Summarize what it is (repo, article, tool, announcement)\n"
                    f"2. Explain why it might matter to the user's projects\n"
                    f"3. If it's a GitHub repo: note stars, language, last update, and what problem it solves\n"
                    f"4. If it links to other interesting repos or tools, mention those too\n"
                    f"Be concise and factual."
                ),
            }
        ]
        response = await self._run_agent_loop(messages)
        await self.conversation.add("assistant", response)

        await self.preferences.record_signal(
            signal_type="tip_submitted",
            topic="user_tip",
            source_name="User Tip",
        )

        # Store the tip as an article so it appears in the review page
        for url in urls:
            await self.db.insert_article(
                url=url,
                title=f"User tip: {user_message[:100]}",
                content=response[:500],
                source_name="User Tip",
                source_type="tip",
            )

        return response

    async def search_on_demand(self, query: str) -> str:
        """Handle an on-demand search request from the user."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Search for: {query}\n\n"
                    f"Use search_web and search_github tools to find relevant results. "
                    f"Summarize the most important findings with links."
                ),
            }
        ]
        return await self._run_agent_loop(messages)

    async def collect_from_sources(self) -> int:
        """Collect from social sources. Repos surface via what people are talking about, not GitHub search."""
        from tools.fetch_rss import fetch_rss
        from tools.fetch_hackernews import fetch_hackernews
        from tools.fetch_reddit import fetch_reddit
        from tools.fetch_twitter import fetch_twitter

        new_count = 0

        # RSS - company announcements only
        feeds = []
        for group_feeds in self._sources_config.get("rss", {}).values():
            if isinstance(group_feeds, list):
                feeds.extend(group_feeds)
        if feeds:
            articles = await fetch_rss(feeds)
            for a in articles:
                result = await self.db.insert_article(**{k: a[k] for k in
                    ("url", "title", "content", "source_name", "source_type", "published_at")})
                if result:
                    new_count += 1

        # Hacker News - repos and tools surface here organically
        hn_config = self._sources_config.get("hackernews", {})
        hn_articles = await fetch_hackernews(
            keywords=hn_config.get("keywords", []),
            max_results=30,
        )
        for a in hn_articles:
            result = await self.db.insert_article(
                url=a["url"], title=a["title"], content=a["content"],
                source_name=a["source_name"], source_type=a["source_type"],
            )
            if result:
                new_count += 1

        # Reddit - practitioner subs where people share repos and tools
        subs = self._sources_config.get("reddit", {}).get("subreddits", [])
        if subs:
            reddit_articles = await fetch_reddit(subs)
            for a in reddit_articles:
                result = await self.db.insert_article(
                    url=a["url"], title=a["title"], content=a["content"],
                    source_name=a["source_name"], source_type=a["source_type"],
                )
                if result:
                    new_count += 1

        # Twitter
        accounts = self._sources_config.get("twitter", {}).get("accounts", [])
        if accounts:
            tweets = await fetch_twitter(accounts)
            for a in tweets:
                result = await self.db.insert_article(
                    url=a["url"], title=a["title"], content=a["content"],
                    source_name=a["source_name"], source_type=a["source_type"],
                )
                if result:
                    new_count += 1

        logger.info(f"Collected {new_count} new articles from sources")
        return new_count

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from a response that may contain markdown code blocks."""
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0]
        return text.strip()
