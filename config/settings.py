import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
USER_CONFIG_DIR = BASE_DIR / "user_config"
DATA_DIR = BASE_DIR / "data"

# LLM
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# APIs
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Schedule
TIMEZONE = os.getenv("TIMEZONE", "UTC")
MORNING_DIGEST_HOUR = int(os.getenv("MORNING_DIGEST_HOUR", "8"))
MORNING_DIGEST_MINUTE = int(os.getenv("MORNING_DIGEST_MINUTE", "0"))
EVENING_DIGEST_HOUR = int(os.getenv("EVENING_DIGEST_HOUR", "18"))
EVENING_DIGEST_MINUTE = int(os.getenv("EVENING_DIGEST_MINUTE", "0"))
SOURCE_SCAN_INTERVAL_HOURS = int(os.getenv("SOURCE_SCAN_INTERVAL_HOURS", "2"))
DISCOVERY_INTERVAL_HOURS = int(os.getenv("DISCOVERY_INTERVAL_HOURS", "6"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Database
DB_PATH = DATA_DIR / "agent.db"

# Digest settings
MAX_ARTICLES_PER_CATEGORY = 5
MIN_SCORE_THRESHOLD = 3.0
