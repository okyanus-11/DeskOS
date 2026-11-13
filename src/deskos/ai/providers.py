"""HTTP providers for DeskAI (no vendor SDKs required).

* ``openai``      — any OpenAI-compatible ``/chat/completions`` endpoint
                    (OpenAI, OpenRouter, LM Studio, vLLM, …)
* ``anthropic``   — Anthropic Messages API
* ``ollama``      — a local Ollama server (no API key)

Keys are read from the OS credential store at request time and never written to
the configuration file.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from deskos.ai.base import AIProvider, AIProviderError, ChatMessage, ProviderConfig

log = logging.getLogger(__name__)


def _post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", "DeskOS/1.0")
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:600]
        except Exception:
            pass
        raise AIProviderError(f"HTTP {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise AIProviderError(f"Network error: {exc.reason}") from exc
    except TimeoutError as exc:
        raise AIProviderError("The request timed out") from exc
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AIProviderError("The provider returned something that is not JSON") from exc
    if not isinstance(parsed, dict):
        raise AIProviderError("Unexpected response shape from the provider")
    return parsed


class OpenAICompatibleProvider(AIProvider):
    name = "openai"
    label = "OpenAI-compatible"
    requires_key = True
    default_models = ("gpt-4o-mini", "gpt-4o", "gpt-4.1-mini")
    docs_url = "https://platform.openai.com/api-keys"

    @property
    def description(self) -> str:
        return "Works with OpenAI, OpenRouter, LM Studio and any /chat/completions server."

    def chat(self, messages: list[ChatMessage], system: str = "") -> str:
        self.validate()
        base = (self.config.base_url or "https://api.openai.com/v1").rstrip("/")
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": ([{"role": "system", "content": system}] if system else [])
            + [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        response = _post_json(f"{base}/chat/completions", payload, headers, self.config.timeout)
        try:
            choice = response["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("The provider response did not contain a message") from exc
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("The provider returned an empty reply")
        return content.strip()


class AnthropicProvider(AIProvider):
    name = "anthropic"
    label = "Anthropic Claude"
    requires_key = True
    default_models = ("claude-sonnet-4-5", "claude-haiku-4-5", "claude-opus-4-1")
    docs_url = "https://console.anthropic.com/settings/keys"

    @property
    def description(self) -> str:
        return "Claude models through the Anthropic Messages API."

    def chat(self, messages: list[ChatMessage], system: str = "") -> str:
        self.validate()
        base = (self.config.base_url or "https://api.anthropic.com/v1").rstrip("/")
        payload: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": [
                {"role": m.role, "content": m.content}
                for m in messages
                if m.role in ("user", "assistant")
            ],
        }
        if system:
            payload["system"] = system
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
        }
        response = _post_json(f"{base}/messages", payload, headers, self.config.timeout)
        blocks = response.get("content") or []
        texts = [
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        content = "\n".join(text for text in texts if text).strip()
        if not content:
            raise AIProviderError("The provider returned an empty reply")
        return content


class OllamaProvider(AIProvider):
    name = "ollama"
    label = "Ollama (local)"
    requires_key = False
    default_models = ("llama3.1", "qwen2.5", "mistral")
    docs_url = "https://ollama.com/download"

    @property
    def description(self) -> str:
        return "Runs models locally through Ollama — no API key, no cloud calls."

    def validate(self) -> None:
        if not self.config.model:
            raise AIProviderError("Choose an Ollama model first")

    def chat(self, messages: list[ChatMessage], system: str = "") -> str:
        self.validate()
        base = (self.config.base_url or "http://localhost:11434").rstrip("/")
        payload: dict[str, Any] = {
            "model": self.config.model,
            "stream": False,
            "options": {"temperature": self.config.temperature},
            "messages": ([{"role": "system", "content": system}] if system else [])
            + [{"role": m.role, "content": m.content} for m in messages],
        }
        response = _post_json(f"{base}/api/chat", payload, {}, self.config.timeout)
        message = response.get("message") or {}
        content = message.get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("Ollama returned an empty reply")
        return content.strip()


PROVIDER_CLASSES: dict[str, type[AIProvider]] = {
    "openai": OpenAICompatibleProvider,
    "anthropic": AnthropicProvider,
    "ollama": OllamaProvider,
}


def create_provider(name: str, config: ProviderConfig) -> AIProvider:
    """Instantiate a provider by name, falling back to OpenAI-compatible."""
    provider_class = PROVIDER_CLASSES.get(name, OpenAICompatibleProvider)
    return provider_class(config)
