from config import settings
from llm.base import LLMProvider
from llm.anthropic import AnthropicProvider
from llm.openai_compat import OpenAICompatProvider


def create_llm_provider() -> LLMProvider:
    """Create an LLM provider based on configuration."""
    provider = settings.LLM_PROVIDER.lower()

    if provider == "anthropic":
        return AnthropicProvider(
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
        )
    elif provider in ("openai", "ollama", "custom"):
        return OpenAICompatProvider(
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
            base_url=settings.LLM_BASE_URL,
        )
    else:
        raise ValueError(
            f"Unknown LLM provider: {provider}. "
            f"Supported: anthropic, openai, ollama, custom"
        )
