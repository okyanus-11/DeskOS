"""DeskAI orchestration: context building, request threading and history."""

from __future__ import annotations

import logging
import platform
from typing import Any

from PySide6.QtCore import QObject, Signal

from deskos.ai.base import AIProviderError, ChatMessage, ProviderConfig
from deskos.ai.credentials import CredentialStore
from deskos.ai.providers import PROVIDER_CLASSES, create_provider
from deskos.core.context import DeskOSContext
from deskos.core.logging_setup import tail_log
from deskos.data.repositories import AIHistoryRepository
from deskos.utils.formatting import format_bytes, format_duration
from deskos.utils.workers import run_async

log = logging.getLogger(__name__)

BASE_SYSTEM_PROMPT = (
    "You are DeskAI, the assistant built into DeskOS, a desktop companion for Windows. "
    "Be concise, practical and honest. Never claim you executed a command or changed the "
    "user's system. When you suggest a terminal command, put it in a fenced code block and "
    "explain what it does. Prefer PowerShell on Windows unless asked otherwise."
)


class AIService(QObject):
    started = Signal(int)  # conversation id
    completed = Signal(int, str)  # conversation id, reply
    failed = Signal(int, str)

    def __init__(self, context: DeskOSContext, history: AIHistoryRepository, parent=None) -> None:
        super().__init__(parent)
        self.ctx = context
        self.history = history
        self.credentials = CredentialStore()
        self._pending: set[int] = set()

    # ------------------------------------------------------------------ config
    def provider_name(self) -> str:
        return str(self.ctx.config.get("ai.provider", "openai"))

    def provider_label(self) -> str:
        provider_class = PROVIDER_CLASSES.get(self.provider_name())
        return provider_class.label if provider_class else self.provider_name()

    def build_provider(self) -> Any:
        name = self.provider_name()
        config = ProviderConfig(
            name=name,
            model=str(self.ctx.config.get("ai.model", "")),
            base_url=str(self.ctx.config.get("ai.base_url", "")),
            api_key=self.credentials.get(name),
            temperature=float(self.ctx.config.get("ai.temperature", 0.4)),
            max_tokens=1024,
            timeout=90.0,
        )
        return create_provider(name, config)

    def has_credentials(self) -> bool:
        name = self.provider_name()
        provider_class = PROVIDER_CLASSES.get(name)
        if provider_class is not None and not provider_class.requires_key:
            return True
        return self.credentials.has_key(name)

    def set_api_key(self, key: str) -> None:
        self.credentials.set(self.provider_name(), key)

    # ----------------------------------------------------------------- context
    def build_context(self) -> str:
        """Real system information + recent log lines for the system prompt."""
        lines: list[str] = []
        try:
            snapshot = self.ctx.monitor.latest
            if snapshot is not None:
                lines.append(
                    "Live system: CPU {:.0f}%, memory {:.0f}% ({} of {}), uptime {}.".format(
                        snapshot.cpu_percent,
                        snapshot.memory_percent,
                        format_bytes(snapshot.memory_used),
                        format_bytes(snapshot.memory_total),
                        format_duration(snapshot.uptime),
                    )
                )
                if snapshot.disks:
                    disk = snapshot.disks[0]
                    lines.append(
                        f"Primary disk {disk['mountpoint']} is {disk['percent']:.0f}% full "
                        f"({format_bytes(disk['free'])} free)."
                    )
            else:
                lines.append("Live system: no sample collected yet.")
        except Exception:
            log.debug("system context unavailable", exc_info=True)

        try:
            os_info = self.ctx.platform.system.os_info()
            lines.append(
                "Platform: {} {} ({}), host {}.".format(
                    os_info.get("name", platform.system()),
                    os_info.get("release", ""),
                    os_info.get("architecture", ""),
                    os_info.get("hostname", ""),
                )
            )
        except Exception:
            lines.append(f"Platform: {platform.platform()}.")

        if self.ctx.config.get("ai.include_logs", True):
            tail = tail_log(40)
            if tail.strip():
                lines.append("Recent DeskOS log lines (most recent last):\n" + tail[-4000:])

        return "\n".join(lines)

    def system_prompt(self, extra_context: str = "") -> str:
        custom = str(self.ctx.config.get("ai.system_prompt", "")).strip()
        parts = [custom or BASE_SYSTEM_PROMPT, BASE_SYSTEM_PROMPT if custom else ""]
        if tool_notes := self.ctx.services.get("ai_tool_notes"):
            parts.append(str(tool_notes))
        context = self.build_context()
        if context:
            parts.append("Context you may use:\n" + context)
        if extra_context:
            parts.append(extra_context)
        return "\n\n".join(part for part in parts if part)

    # ---------------------------------------------------------------- messages
    def send(self, conversation_id: int, text: str, extra_context: str = "") -> int:
        """Persist the user message and request a reply in the background."""
        text = text.strip()
        if not text:
            return conversation_id
        if conversation_id <= 0:
            conversation_id = self.history.create_conversation(
                title=text[:48], provider=self.provider_name(), model=str(self.ctx.config.get("ai.model", ""))
            )
        self.history.add_message(conversation_id, "user", text)
        self._pending.add(conversation_id)
        self.started.emit(conversation_id)
        run_async(
            self._request,
            lambda reply: self._on_reply(conversation_id, reply),
            lambda error: self._on_error(conversation_id, error),
            conversation_id,
            extra_context,
        )
        return conversation_id

    def _request(self, conversation_id: int, extra_context: str) -> str:
        provider = self.build_provider()
        limit = int(self.ctx.config.get("ai.max_context_messages", 20))
        raw = self.history.messages(conversation_id, limit=limit)
        messages = [
            ChatMessage(role=str(item["role"]), content=str(item["content"]))
            for item in raw
            if item["role"] in ("user", "assistant")
        ]
        if not messages:
            raise AIProviderError("There is nothing to send yet")
        return provider.chat(messages, self.system_prompt(extra_context))

    def _on_reply(self, conversation_id: int, reply: str) -> None:
        self._pending.discard(conversation_id)
        self.history.add_message(conversation_id, "assistant", reply)
        self.completed.emit(conversation_id, reply)

    def _on_error(self, conversation_id: int, message: str) -> None:
        self._pending.discard(conversation_id)
        log.warning("DeskAI request failed: %s", message)
        self.failed.emit(conversation_id, message)

    def is_pending(self, conversation_id: int) -> bool:
        return conversation_id in self._pending

    # --------------------------------------------------------------- shortcuts
    def explain_error_prompt(self) -> str:
        error = str(self.ctx.services.get("last_error") or "").strip()
        if not error:
            return (
                "DeskOS has not recorded an unhandled error this session. "
                "Ask me anything about DeskOS instead."
            )
        return (
            "Explain this DeskOS error and how to fix it. Do not run anything:\n\n"
            f"```\n{error[-3000:]}\n```"
        )

    def summarize_logs_prompt(self) -> str:
        tail = tail_log(120)
        if not tail.strip():
            return "The DeskOS log file is empty or unavailable right now."
        return (
            "Summarise these DeskOS log lines: highlight errors, warnings and anything "
            "the user should act on.\n\n"
            f"```\n{tail[-6000:]}\n```"
        )

    def new_conversation(self) -> int:
        return self.history.create_conversation(
            title="New conversation",
            provider=self.provider_name(),
            model=str(self.ctx.config.get("ai.model", "")),
        )
