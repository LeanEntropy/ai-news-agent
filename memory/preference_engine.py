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
