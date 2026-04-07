from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class AgentResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] | None = None,
    ) -> AgentResponse:
        """Send a chat completion request with optional tool definitions.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            system: System prompt.
            tools: List of tool schemas the model can call.

        Returns:
            AgentResponse with content and/or tool calls.
        """
        ...
