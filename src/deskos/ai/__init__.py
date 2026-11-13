"""DeskAI — optional assistant with pluggable providers."""

from deskos.ai.base import AIProvider, AIProviderError, ChatMessage
from deskos.ai.service import AIService

__all__ = ["AIProvider", "AIProviderError", "ChatMessage", "AIService"]
