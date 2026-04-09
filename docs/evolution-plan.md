# AI News Agent - Evolution Plan

## Vision

A focused, periodic intelligence agent that scans sources on schedule, finds projects and news relevant to the user, evaluates fit against active projects, delivers clear actionable summaries, holds conversations about findings, and evolves its understanding of the user over time.

**Not** a general-purpose personal assistant. Not always-on. Not OpenClaw.

---

## Current State

The agent already has:
- Scheduled source scanning (RSS, HN, Reddit, Twitter, GitHub) via APScheduler
- Telegram bot with conversation support and commands
- LLM-powered digest compilation with category scoring
- Project-aware repo discovery
- Deep dive article analysis (browse + summarize)
- Basic preference learning from explicit feedback buttons (relevant / not for me)
- Multi-LLM support (Anthropic, OpenAI, Ollama, custom)

## What's Missing

### 1. Memory is shallow
- `ConversationMemory` = last 30 messages in a flat list
- No long-term memory across sessions
- Agent can't reference past conversations ("last week you mentioned...")
- No persistent knowledge about the user beyond static YAML files

### 2. Preference learning is too simplistic
- Only learns from explicit button clicks
- Doesn't learn from conversation content
- No engagement tracking (did user ask for deep dive? did they reply?)
- No decay of stale preferences
- No per-topic or per-source scoring

### 3. User model is static
- `profile.yaml` and `projects.yaml` are hand-edited files
- Agent can't update its understanding when user says "I dropped the Unity project"
- Interests can't evolve without manual file edits

### 4. No conversation-to-knowledge pipeline
- Conversations contain valuable signals (tools being evaluated, problems, likes/dislikes)
- None of that gets extracted into persistent understanding
- Every conversation is throwaway context

### 5. Scoring doesn't learn from history
- Articles scored in isolation each time
- No "articles about X consistently get 'not for me' so stop surfacing X"
- No feedback loop from delivery outcomes to scoring weights

---

## Implementation Plan

### Phase 1: Persistent Knowledge Memory

**Goal:** The agent remembers important things across sessions and uses them in future interactions.

**Files to create/modify:**
- `memory/knowledge.py` (new) - Knowledge extraction and storage
- `memory/store.py` - Add `knowledge` table to schema

**Schema:**
```sql
CREATE TABLE knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,        -- 'user_fact', 'project_update', 'preference', 'tool_opinion', 'topic_interest'
    content TEXT NOT NULL,          -- The actual knowledge ("user is evaluating Rust for backend rewrite")
    source TEXT DEFAULT '',         -- Where this came from: 'conversation', 'feedback', 'inference'
    importance REAL DEFAULT 1.0,    -- 0.0 to 2.0, decays over time
    access_count INTEGER DEFAULT 0, -- How often this knowledge has been used
    created_at TEXT NOT NULL,
    last_accessed TEXT NOT NULL,
    expires_at TEXT DEFAULT NULL    -- Optional hard expiry
);
```

**Knowledge extraction flow:**
1. After each conversation, send the conversation to the LLM with a prompt: "Extract any facts, preferences, project updates, or opinions the user expressed. Return structured knowledge items."
2. Store extracted items in the knowledge table
3. Before each agent interaction, retrieve top-N relevant knowledge items by importance and inject them into the system prompt
4. Periodically decay importance: `importance *= 0.95` daily for items not accessed in 7+ days
5. Remove items where `importance < 0.3` and `access_count < 2`

**What this enables:**
- "Last week you said you were evaluating LangGraph - here's a comparison article"
- "You mentioned Unity gives you grief with hot reload - this new plugin addresses that"
- Agent retains context across days/weeks without needing always-on state

---

### Phase 2: Adaptive Preference Engine

**Goal:** The agent learns what the user actually cares about from all signals, not just button clicks.

**Files to create/modify:**
- `memory/preference_engine.py` (new) - Multi-signal preference learning
- `memory/store.py` - Add `engagement_signals` table
- `agent/core.py` - Integrate engagement tracking

**Schema:**
```sql
CREATE TABLE engagement_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER,
    signal_type TEXT NOT NULL,      -- 'feedback_positive', 'feedback_negative', 'deep_dive', 
                                    -- 'conversation_mention', 'ignored', 'follow_up_question'
    topic TEXT DEFAULT '',          -- Extracted topic/keyword
    source_name TEXT DEFAULT '',    -- Which source this came from
    category TEXT DEFAULT '',       -- Article category
    weight REAL DEFAULT 1.0,       -- Signal strength (deep_dive > button click > ignore)
    timestamp TEXT NOT NULL
);

CREATE TABLE topic_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL UNIQUE,
    score REAL DEFAULT 0.0,         -- Running score: positive = interested, negative = not interested
    sample_count INTEGER DEFAULT 0, -- How many signals contributed
    last_updated TEXT NOT NULL
);

CREATE TABLE source_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL UNIQUE,
    score REAL DEFAULT 0.0,         -- Source reliability/interest score
    hit_count INTEGER DEFAULT 0,    -- Items from this source user engaged with
    miss_count INTEGER DEFAULT 0,   -- Items from this source user ignored/rejected
    last_updated TEXT NOT NULL
);
```

**Signal weights:**
```
deep_dive_requested:    +3.0   (strongest positive signal)
feedback_positive:      +2.0
follow_up_question:     +1.5
conversation_mention:   +1.0
no_reaction:            -0.2   (mild negative - ignored)
feedback_negative:      -2.0
explicit_mute:          -5.0   (user says "stop showing me X")
```

**Preference engine flow:**
1. Collect signals from all interactions (not just buttons)
2. Aggregate into `topic_scores` and `source_scores` with exponential moving average
3. When scoring articles for digest, multiply by topic and source adjustments
4. Apply time decay: recent signals weigh more than old ones
5. Expose via `/preferences` command with clear explanations

**What this enables:**
- Agent stops surfacing topics user consistently ignores
- Agent boosts sources that produce items user engages with
- Preferences evolve naturally from behavior, not just explicit clicks

---

### Phase 3: Evolving User Model

**Goal:** The agent updates its understanding of user projects and interests from conversations, not just static YAML.

**Files to create/modify:**
- `memory/user_profile.py` - Add dynamic overlay on top of static YAML
- `memory/store.py` - Add `profile_updates` table
- `agent/prompts.py` - Include dynamic profile in system prompt

**Schema:**
```sql
CREATE TABLE profile_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    field TEXT NOT NULL,            -- 'project_added', 'project_removed', 'project_updated',
                                    -- 'interest_added', 'interest_removed', 'avoid_added'
    key TEXT NOT NULL,              -- Project name or interest topic
    value TEXT DEFAULT '',          -- JSON with details
    confidence REAL DEFAULT 0.8,   -- How sure the agent is about this update
    created_at TEXT NOT NULL,
    confirmed INTEGER DEFAULT 0    -- 1 if user explicitly confirmed
);
```

**Flow:**
1. During knowledge extraction (Phase 1), also detect profile-level changes:
   - "I started a new project in Rust" -> `project_added`
   - "I'm done with the game dev stuff" -> `project_removed` or `interest_removed`
   - "I'm now more interested in infra than frontend" -> `interest_added` + weight shift
2. For high-confidence changes (explicit statements), apply immediately
3. For inferred changes (mentioned Rust 5 times this week), apply with lower confidence
4. `UserProfile.get_profile_summary()` merges static YAML + dynamic updates
5. User can review and confirm/reject via `/profile` command
6. Confirmed updates get `confidence = 1.0` and persist permanently

**What this enables:**
- "Since you started the Rust project, I found these memory-safe concurrency libs"
- Agent naturally shifts what it surfaces as user's focus evolves
- No need to manually edit YAML files

---

### Phase 4: Smarter Scoring & Delivery

**Goal:** Use all accumulated knowledge to score articles better and optimize delivery format/timing.

**Files to modify:**
- `agent/core.py` - Enhanced scoring with preference data
- `agent/prompts.py` - Richer scoring prompt with learned context
- `delivery/formatter.py` - Adaptive formatting
- `tasks/scheduler.py` - Delivery timing optimization

**Enhanced scoring prompt:**
```
When scoring articles, consider:
1. User's current projects and pain points (from evolving profile)
2. Topic scores (from preference engine): {topic_scores}
3. Source reliability (from source scores): {source_scores}
4. Recent knowledge (from knowledge memory): {recent_knowledge}
5. Previously delivered similar items (avoid repeats)

Penalize:
- Topics with negative scores
- Sources with low hit rates
- Items similar to recently delivered content
- Hype/speculation (user preference)

Boost:
- Direct project relevance with specific reasoning
- Topics with high positive scores
- Emerging trends in user's interest areas
- Actionable items (tools, libraries, techniques they can use today)
```

**Delivery optimization:**
- Track which digest periods get more engagement (morning vs evening)
- Track optimal number of items (too many = ignored, too few = unsatisfying)
- Store delivery metadata: `{period, item_count, engagement_rate}`
- Adjust over time: if morning digests get 80% engagement but evening gets 20%, suggest shifting to morning-only
- Add `/settings` command for user to configure delivery preferences

**Formatting improvements:**
- For PROJECT_RELEVANT items, include specific code/tech details
- For discoveries, include "how to try it" section
- Group by actionability: "Try today" vs "Keep on radar" vs "FYI"
- Adaptive length: if user consistently deep-dives, include more detail upfront

---

### Phase 5: Conversation Intelligence

**Goal:** Make conversations smarter - agent uses everything it knows when chatting.

**Files to modify:**
- `agent/core.py` - Enhanced conversation context
- `agent/prompts.py` - Conversation-aware system prompt
- `memory/conversation.py` - Smarter context windowing

**Enhanced conversation context:**
1. Before responding to any message, assemble context:
   - Last N messages (current conversation window)
   - Relevant knowledge items (semantic match against user's message)
   - Recent digest items the user might be referring to
   - Active project details
   - Relevant topic/source scores
2. Inject as structured context in system prompt, not just flat message history

**Conversation summarization:**
1. When conversation history exceeds 30 messages, summarize older messages
2. Store summary as a knowledge item with `category = 'conversation_summary'`
3. Keep summaries in rotation for 30 days, then decay
4. This gives the agent long-term conversational memory without unbounded context

**Smart follow-ups:**
- If user asks about an article from the digest, auto-fetch the full article
- If user asks "what else is like X", search based on the article's topics
- If user says "remind me about this", store as a knowledge item with future relevance

---

## Implementation Order & Dependencies

```
Phase 1: Persistent Knowledge Memory
   |
   v
Phase 2: Adaptive Preference Engine  (can run in parallel with Phase 1)
   |
   v
Phase 3: Evolving User Model  (depends on Phase 1 for knowledge extraction)
   |
   v
Phase 4: Smarter Scoring & Delivery  (depends on Phase 2 + 3 for preference data)
   |
   v
Phase 5: Conversation Intelligence  (depends on Phase 1 + 2 for context assembly)
```

**Phases 1 and 2 can be implemented in parallel.** Phase 3 builds on Phase 1. Phases 4 and 5 integrate everything.

## Estimated Scope

| Phase | New Code | Modified Files | New Tables |
|-------|----------|---------------|------------|
| 1 | ~200 lines | store.py, core.py, prompts.py | knowledge |
| 2 | ~250 lines | store.py, core.py, bot.py | engagement_signals, topic_scores, source_scores |
| 3 | ~150 lines | user_profile.py, store.py, prompts.py, bot.py | profile_updates |
| 4 | ~150 lines | core.py, prompts.py, formatter.py, scheduler.py | delivery_stats |
| 5 | ~150 lines | core.py, prompts.py, conversation.py | (uses knowledge table) |
| **Total** | **~900 lines** | | **6 new tables** |

## Design Principles

1. **Stay focused** - This is a news intelligence agent, not a personal assistant
2. **Learn from behavior** - Every interaction is a signal, not just explicit feedback
3. **Decay stale knowledge** - Interests change, old preferences should fade
4. **Confirm before assuming** - High-impact profile changes should be confirmed by user
5. **Keep it simple** - No microservices, no message brokers, no containers. Python + SQLite + APScheduler
6. **Multi-LLM stays** - All enhancements work with any OpenAI-compatible API

## Patterns Borrowed from OpenClaw

| OpenClaw Pattern | Our Adaptation |
|---|---|
| Memory importance scoring + decay | Phase 1: knowledge table with importance field and periodic decay |
| Action outcome learning | Phase 2: multi-signal engagement tracking, not just button clicks |
| HEARTBEAT.md proactive judgment | Not adopted - we use scheduled scans, not ambient awareness |
| SOUL.md personality file | Not adopted - our prompts.py system prompt is sufficient |
| Conversation-to-memory pipeline | Phase 1 + 5: extract knowledge from conversations, use in future context |

## Not In Scope

- Always-on agent behavior (HEARTBEAT.md style)
- Multi-platform support (Telegram only for now)
- Multi-user support
- Container isolation
- Model fine-tuning / weight adaptation (OpenClaw-RL)
- Skill/plugin marketplace
