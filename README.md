# AI News Agent

An autonomous AI agent that monitors the AI landscape and delivers personalized intelligence via Telegram. Not a dumb news aggregator - it **reasons** about what matters to you, proactively discovers tools relevant to your projects, and learns your preferences over time.

## What It Does

- **Curated digests** twice daily with top AI news, domain-specific updates, and discoveries
- **Proactive discovery** - searches GitHub for repos and tools that could help your active projects
- **Conversational** - ask it questions, request searches, discuss findings via Telegram
- **Preference learning** - adapts to your feedback (relevant/not for me) to improve over time
- **Multi-source** - RSS feeds, Hacker News, Reddit, GitHub trending, Twitter/X (via RSSHub)
- **LLM-agnostic** - works with Claude, GPT, Gemini, Ollama, or any OpenAI-compatible API
- **No drama** - strips hype and speculation, delivers facts and links

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/civax/ai-news-agent.git
cd ai-news-agent

# Set up environment
cp .env.example .env
# Edit .env with your API keys and Telegram bot token

# Set up your profile
cp user_config/profile.yaml.example user_config/profile.yaml
cp user_config/projects.yaml.example user_config/projects.yaml
# Edit these files to describe your interests and projects
```

### 2. Get a Telegram Bot Token

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the token to `TELEGRAM_BOT_TOKEN` in `.env`
4. Message [@userinfobot](https://t.me/userinfobot) to get your chat ID
5. Set `TELEGRAM_CHAT_ID` in `.env`

### 3. Run with Docker

```bash
docker-compose up -d
```

### Or run directly

```bash
pip install -r requirements.txt
python main.py
```

## Configuration

### Environment Variables (.env)

| Variable | Required | Description |
|----------|----------|-------------|
| `LLM_PROVIDER` | Yes | `anthropic`, `openai`, `ollama`, or `custom` |
| `LLM_MODEL` | Yes | Model name (e.g., `claude-sonnet-4-20250514`, `gpt-4o`) |
| `LLM_API_KEY` | Yes | API key for your LLM provider |
| `LLM_BASE_URL` | For ollama/custom | API endpoint URL |
| `TELEGRAM_BOT_TOKEN` | Yes | From @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | Your Telegram chat ID |
| `TAVILY_API_KEY` | Recommended | For web search (free tier at tavily.com) |
| `GITHUB_TOKEN` | Recommended | Increases GitHub API rate limits |

### User Profile (user_config/profile.yaml)

Define who you are and what you care about:

```yaml
name: "Your Name"
role: "Your role"
interests:
  primary: ["AI agents", "game development"]
  secondary: ["open source", "startups"]
  avoid: ["hype pieces", "speculation"]
tone: "Direct, no bullshit. Facts and links only."
```

### Projects (user_config/projects.yaml)

Describe your active projects so the agent can find relevant tools:

```yaml
projects:
  - name: "My Project"
    description: "What it does"
    tech_stack: ["python", "pytorch"]
    pain_points: ["slow inference", "memory issues"]
    looking_for: ["optimization tools", "memory management"]
```

### Sources (user_config/sources.yaml)

Override or extend the default source list.

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/digest` | Get a digest right now |
| `/search <query>` | Search for repos, tools, or news |
| `/status` | Agent statistics |
| `/preferences` | View learned preferences |
| `/help` | Show available commands |

Or just send any message to chat with the agent.

## Architecture

```
User Layer (profile.yaml, projects.yaml, learned preferences)
    ↓
Agent Core (LLM-powered reasoning with tool use)
    ↓
Tools (web search, GitHub, RSS, HN, Reddit, Twitter)
    ↓
Delivery (Telegram with feedback buttons)
    ↓
Preference Learning (adapts from feedback)
```

## Digest Format

```
MORNING BRIEFING - Apr 7, 2026

TOP NEWS
━━━━━━━━
Claude 4.5 released with native computer use
→ anthropic.com/news/claude-4-5

AI + GAME DEV
━━━━━━━━━━━━
New MCP server for Unity Editor control
→ github.com/x/unity-mcp-tools (234 stars)

FOR YOUR PROJECTS
━━━━━━━━━━━━━━━━
agent-memory-graph - graph-based memory for AI agents
Why: Could solve context loss in your art direction tool
→ github.com/x/agent-memory-graph

NOTABLE
━━━━━━━
• Google open-sources Gemma 3 9B
• NVIDIA GameGen-X paper
```

## LLM Providers

| Provider | Config |
|----------|--------|
| Claude | `LLM_PROVIDER=anthropic` |
| GPT-4o | `LLM_PROVIDER=openai` |
| Gemini | `LLM_PROVIDER=custom`, set `LLM_BASE_URL` |
| Ollama | `LLM_PROVIDER=ollama`, `LLM_BASE_URL=http://localhost:11434/v1` |
| Any OpenAI-compatible | `LLM_PROVIDER=custom`, set `LLM_BASE_URL` |

## License

MIT
