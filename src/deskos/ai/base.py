"""Provider interface and shared message model for DeskAI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class AIProviderError(RuntimeError):
    """Raised when a provider request fails."""


@dataclass
class ChatMessage:
    role: str  # user | assistant | system
    content: str


@dataclass
class ProviderConfig:
    name: str
    model: str
    base_url: str = ""
    api_key: str = ""
    temperature: float = 0.4
    max_tokens: int = 1024
    timeout: float = 60.0
    extra: dict = field(default_factory=dict)


class AIProvider(ABC):
    """A chat completion backend."""

    name: str = "provider"
    label: str = "Provider"
    requires_key: bool = True
    default_models: tuple[str, ...] = ()
    docs_url: str = ""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    @abstractmethod
    def chat(self, messages: list[ChatMessage], system: str = "") -> str:
        """Return the assistant's reply for ``messages``."""

    def validate(self) -> None:
        if self.requires_key and not self.config.api_key:
            raise AIProviderError(
                f"{self.label} needs an API key — add one in DeskAI settings"
            )
        if not self.config.model:
            raise AIProviderError("No model selected")

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def description(self) -> str:
        return ""
