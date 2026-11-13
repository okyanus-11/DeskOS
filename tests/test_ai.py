"""DeskAI providers, credential handling and context building."""

from __future__ import annotations

import json
import time

import pytest

from deskos.ai import providers
from deskos.ai.base import AIProviderError, ChatMessage, ProviderConfig
from deskos.ai.credentials import CredentialStore
from deskos.ai.providers import (
    AnthropicProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    create_provider,
)
from deskos.ai.service import AIService


def provider_config(**overrides) -> ProviderConfig:
    defaults = {
        "name": "openai",
        "model": "gpt-4o-mini",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test",
        "temperature": 0.2,
        "max_tokens": 256,
        "timeout": 5.0,
    }
    defaults.update(overrides)
    return ProviderConfig(**defaults)


def test_openai_compatible_request_and_reply(monkeypatch):
    captured = {}

    def fake_post(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        return {"choices": [{"message": {"content": "  hello there  "}}]}

    monkeypatch.setattr(providers, "_post_json", fake_post)
    provider = OpenAICompatibleProvider(provider_config())
    reply = provider.chat([ChatMessage("user", "hi")], system="be nice")
    assert reply == "hello there"
    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["payload"]["messages"][0] == {"role": "system", "content": "be nice"}
    assert captured["headers"]["Authorization"] == "Bearer sk-test"


def test_openai_requires_key():
    provider = OpenAICompatibleProvider(provider_config(api_key=""))
    with pytest.raises(AIProviderError):
        provider.chat([ChatMessage("user", "hi")])


def test_openai_malformed_response(monkeypatch):
    monkeypatch.setattr(providers, "_post_json", lambda *args, **kwargs: {"unexpected": True})
    with pytest.raises(AIProviderError):
        OpenAICompatibleProvider(provider_config()).chat([ChatMessage("user", "hi")])


def test_anthropic_payload_and_reply(monkeypatch):
    captured = {}

    def fake_post(url, payload, headers, timeout):
        captured.update(url=url, payload=payload, headers=headers)
        return {"content": [{"type": "text", "text": "claude says hi"}]}

    monkeypatch.setattr(providers, "_post_json", fake_post)
    provider = AnthropicProvider(
        provider_config(name="anthropic", model="claude-haiku-4-5", api_key="key")
    )
    reply = provider.chat(
        [ChatMessage("system", "ignored"), ChatMessage("user", "hello")], system="system prompt"
    )
    assert reply == "claude says hi"
    assert captured["url"] == "https://api.example.com/v1/messages"
    assert captured["payload"]["system"] == "system prompt"
    assert all(message["role"] != "system" for message in captured["payload"]["messages"])
    assert captured["headers"]["x-api-key"] == "key"


def test_ollama_is_local_and_keyless(monkeypatch):
    captured = {}

    def fake_post(url, payload, headers, timeout):
        captured.update(url=url, payload=payload)
        return {"message": {"content": "local reply"}}

    monkeypatch.setattr(providers, "_post_json", fake_post)
    provider = OllamaProvider(
        provider_config(name="ollama", model="llama3.1", base_url="", api_key="")
    )
    assert provider.chat([ChatMessage("user", "hi")], system="s") == "local reply"
    assert captured["url"] == "http://localhost:11434/api/chat"


def test_provider_factory_fallback():
    provider = create_provider("unknown", provider_config())
    assert isinstance(provider, OpenAICompatibleProvider)


class TestCredentialStore:
    def test_file_fallback_roundtrip(self, tmp_path, monkeypatch):
        store = CredentialStore(fallback_path=tmp_path / "secrets.json")
        store._keyring = None  # force the documented fallback
        assert store.secure_backend is False
        assert store.get("openai") == ""
        assert store.set("openai", "sk-secret") is True
        assert store.get("openai") == "sk-secret"
        payload = json.loads((tmp_path / "secrets.json").read_text())
        assert payload == {"openai": "sk-secret"}
        store.delete("openai")
        assert store.get("openai") == ""

    def test_backend_name_is_reported_honestly(self, tmp_path):
        store = CredentialStore(fallback_path=tmp_path / "secrets.json")
        store._keyring = None
        assert "not OS-protected" in store.backend_name()


class TestAIService:
    def test_context_contains_real_system_information(self, context, qapp, sample_snapshot):
        context.monitor.latest = sample_snapshot
        service = AIService(context, context.ai_history)
        text = service.build_context()
        assert "Live system" in text
        assert "TestOS" in text

    def test_system_prompt_uses_custom_instructions(self, context, qapp):
        context.config.set("ai.system_prompt", "Answer in haiku form.")
        service = AIService(context, context.ai_history)
        prompt = service.system_prompt()
        assert "Answer in haiku form." in prompt

    def test_explain_error_uses_recorded_traceback(self, context, qapp):
        service = AIService(context, context.ai_history)
        assert "has not recorded" in service.explain_error_prompt()
        context.services["last_error"] = "Traceback: boom"
        assert "Traceback: boom" in service.explain_error_prompt()

    def test_api_key_never_written_to_config(self, context, qapp, tmp_path):
        service = AIService(context, context.ai_history)
        service.credentials = CredentialStore(fallback_path=tmp_path / "secrets.json")
        service.credentials._keyring = None
        service.set_api_key("sk-live-secret")
        serialised = json.dumps(context.config.as_dict())
        assert "sk-live-secret" not in serialised
        assert "api_key" not in serialised
        assert service.credentials.get("openai") == "sk-live-secret"

    def test_send_persists_user_message_and_reply(self, context, qapp, monkeypatch):
        service = AIService(context, context.ai_history)
        monkeypatch.setattr(service.credentials, "get", lambda provider: "key")
        conversation = service.new_conversation()

        def fake_chat(self, messages, system=""):
            assert messages[-1].content == "hello"
            assert "Context you may use" in system
            return "hi from provider"

        monkeypatch.setattr(providers.OpenAICompatibleProvider, "chat", fake_chat)
        replies: list[str] = []
        service.completed.connect(lambda _cid, reply: replies.append(reply))
        service.send(conversation, "hello")
        for _ in range(200):
            qapp.processEvents()
            time.sleep(0.01)
            if replies:
                break
        assert replies == ["hi from provider"]
        stored = context.ai_history.messages(conversation)
        assert [message["role"] for message in stored] == ["user", "assistant"]
        assert stored[-1]["content"] == "hi from provider"
