"""DeskAI chat window."""

from __future__ import annotations

import logging
import re

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from deskos.ai.providers import PROVIDER_CLASSES
from deskos.ai.service import AIService
from deskos.core.context import DeskOSContext
from deskos.ui.chrome import DeskWindow
from deskos.ui.components import Card, IconButton, Muted, apply_shadow, scrollable
from deskos.utils.formatting import relative_time

log = logging.getLogger(__name__)

CODE_BLOCK = re.compile(r"```[a-zA-Z0-9]*\n(.*?)```", re.DOTALL)


class ProviderDialog(QDialog):
    """Configure provider, model and API key (key never touches config.json)."""

    def __init__(self, parent: QWidget, service: AIService, context: DeskOSContext) -> None:
        super().__init__(parent)
        self.service = service
        self.ctx = context
        self.setWindowTitle("DeskAI settings")
        self.setMinimumWidth(520)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        panel = QWidget()
        panel.setObjectName("Panel")
        apply_shadow(panel, 44, 10, 120)
        outer.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)

        heading = QLabel("DeskAI configuration")
        heading.setObjectName("Subheading")
        layout.addWidget(heading)

        layout.addWidget(QLabel("Provider"))
        self.provider_combo = QComboBox()
        for name, provider_class in PROVIDER_CLASSES.items():
            self.provider_combo.addItem(provider_class.label, name)
        current = self.ctx.config.get("ai.provider", "openai")
        index = self.provider_combo.findData(current)
        self.provider_combo.setCurrentIndex(max(0, index))
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        layout.addWidget(self.provider_combo)

        self.provider_hint = Muted("")
        layout.addWidget(self.provider_hint)

        layout.addWidget(QLabel("Model"))
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        layout.addWidget(self.model_combo)

        layout.addWidget(QLabel("Base URL (leave blank for the provider default)"))
        self.base_url = QLineEdit(str(self.ctx.config.get("ai.base_url", "")))
        layout.addWidget(self.base_url)

        layout.addWidget(QLabel("API key (stored in your OS credential store)"))
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("Paste a key, or leave blank to keep the stored one")
        layout.addWidget(self.api_key)
        self.key_status = Muted("")
        layout.addWidget(self.key_status)

        layout.addWidget(QLabel("Custom system instructions"))
        self.system_prompt = QTextEdit()
        self.system_prompt.setPlainText(str(self.ctx.config.get("ai.system_prompt", "")))
        self.system_prompt.setMaximumHeight(110)
        layout.addWidget(self.system_prompt)

        self.include_logs = QPushButton("Include recent log lines as context")
        self.include_logs.setCheckable(True)
        self.include_logs.setChecked(bool(self.ctx.config.get("ai.include_logs", True)))
        layout.addWidget(self.include_logs)

        buttons = QHBoxLayout()
        self.secure_label = Muted(service.credentials.backend_name())
        buttons.addWidget(self.secure_label, 1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("Save")
        save.setObjectName("PrimaryButton")
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons.addWidget(save)
        layout.addLayout(buttons)

        self._on_provider_changed(self.provider_combo.currentIndex())

    def _on_provider_changed(self, _index: int) -> None:
        name = str(self.provider_combo.currentData())
        provider_class = PROVIDER_CLASSES.get(name)
        self.model_combo.clear()
        if provider_class is not None:
            self.model_combo.addItems(provider_class.default_models)
            self.provider_hint.setText(provider_class.description)
        stored_model = str(self.ctx.config.get("ai.model", ""))
        if stored_model:
            self.model_combo.setCurrentText(stored_model)
        has_key = self.service.credentials.has_key(name)
        self.key_status.setText(
            "A key is already stored." if has_key else "No key stored for this provider yet."
        )
        self.api_key.setEnabled(provider_class.requires_key if provider_class else True)

    def _save(self) -> None:
        name = str(self.provider_combo.currentData())
        model = self.model_combo.currentText().strip()
        if not model:
            QMessageBox.warning(self, "Missing model", "Choose or type a model name.")
            return
        self.ctx.config.set("ai.provider", name, save=False)
        self.ctx.config.set("ai.model", model, save=False)
        self.ctx.config.set("ai.base_url", self.base_url.text().strip(), save=False)
        self.ctx.config.set("ai.system_prompt", self.system_prompt.toPlainText().strip(), save=False)
        self.ctx.config.set("ai.include_logs", self.include_logs.isChecked(), save=False)
        self.ctx.config.set("ai.enabled", True)
        key = self.api_key.text().strip()
        if key:
            if self.service.credentials.set(name, key):
                self.service.credentials = type(self.service.credentials)()
                self.ctx.toast("API key stored")
            else:
                QMessageBox.warning(
                    self, "Key not stored", "DeskOS could not store the API key."
                )
                return
        self.accept()


class MessageBubble(QWidget):
    def __init__(self, role: str, text: str, icons, theme, on_run=None) -> None:
        super().__init__()
        wrapper = QVBoxLayout(self)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.setSpacing(3)

        header = QLabel("You" if role == "user" else "DeskAI")
        header.setObjectName("StatLabel")
        wrapper.addWidget(header, 0, Qt.AlignmentFlag.AlignLeft if role == "user" else Qt.AlignmentFlag.AlignRight)

        bubble = QWidget()
        bubble.setObjectName("BubbleUser" if role == "user" else "BubbleAssistant")
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(14, 10, 14, 10)
        bubble_layout.setSpacing(6)
        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setMaximumWidth(620)
        bubble_layout.addWidget(body)

        commands = CODE_BLOCK.findall(text)
        if role == "assistant" and commands and on_run is not None:
            run_button = QPushButton("Review command…")
            run_button.setIcon(icons.icon("terminal", 14))
            run_button.setToolTip("DeskAI never runs commands automatically")
            run_button.clicked.connect(lambda: on_run(commands[0].strip()))
            bubble_layout.addWidget(run_button, 0, Qt.AlignmentFlag.AlignLeft)

        wrapper.addWidget(
            bubble, 0, Qt.AlignmentFlag.AlignLeft if role == "user" else Qt.AlignmentFlag.AlignRight
        )


class DeskAIWindow(DeskWindow):
    def __init__(self, context: DeskOSContext) -> None:
        super().__init__(context, "DeskAI", "ai", "Optional assistant")
        self.ctx = context
        self.resize(1080, 720)
        self.setMinimumSize(860, 560)

        self.service = AIService(context, context.ai_history)
        self.service.started.connect(self._on_started)
        self.service.completed.connect(self._on_completed)
        self.service.failed.connect(self._on_failed)
        self._conversation_id = 0
        self._pending_label: QLabel | None = None

        nav = QWidget()
        nav.setObjectName("Sidebar")
        nav.setFixedWidth(210)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(12, 12, 12, 12)
        nav_layout.setSpacing(8)
        new_chat = QPushButton("New conversation")
        new_chat.setObjectName("PrimaryButton")
        new_chat.setIcon(self.ctx.icons.icon("plus", 14, self.ctx.theme.palette.crust))
        new_chat.clicked.connect(self.new_conversation)
        nav_layout.addWidget(new_chat)
        self.conversation_list = QListWidget()
        self.conversation_list.currentItemChanged.connect(self._on_conversation_selected)
        nav_layout.addWidget(self.conversation_list, 1)
        settings_button = QPushButton("DeskAI settings")
        settings_button.setIcon(self.ctx.icons.icon("settings", 14))
        settings_button.clicked.connect(self._open_settings)
        nav_layout.addWidget(settings_button)
        self.body_layout.addWidget(nav)

        chat = QWidget()
        chat_layout = QVBoxLayout(chat)
        chat_layout.setContentsMargins(18, 8, 18, 14)
        chat_layout.setSpacing(10)

        toolbar = QHBoxLayout()
        self.provider_label = QLabel("")
        self.provider_label.setObjectName("Subheading")
        toolbar.addWidget(self.provider_label)
        toolbar.addStretch(1)
        explain = QPushButton("Explain last error")
        explain.setIcon(self.ctx.icons.icon("alert", 14))
        explain.clicked.connect(self._explain_error)
        toolbar.addWidget(explain)
        logs = QPushButton("Summarise logs")
        logs.setIcon(self.ctx.icons.icon("notes", 14))
        logs.clicked.connect(self._summarize_logs)
        toolbar.addWidget(logs)
        chat_layout.addLayout(toolbar)

        self.banner = Card(padding=12)
        banner_row = QHBoxLayout()
        self.banner_label = Muted("")
        banner_row.addWidget(self.banner_label, 1)
        configure = QPushButton("Configure")
        configure.setObjectName("PrimaryButton")
        configure.clicked.connect(self._open_settings)
        banner_row.addWidget(configure)
        self.banner.layout.addLayout(banner_row)
        chat_layout.addWidget(self.banner)

        self.messages_host = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_host)
        self.messages_layout.setContentsMargins(4, 4, 4, 4)
        self.messages_layout.setSpacing(12)
        self.messages_layout.addStretch(1)
        self.messages_area = scrollable(self.messages_host)
        chat_layout.addWidget(self.messages_area, 1)

        input_row = QHBoxLayout()
        self.input = QTextEdit()
        self.input.setPlaceholderText("Ask DeskAI about DeskOS, your system or a command…")
        self.input.setMaximumHeight(88)
        input_row.addWidget(self.input, 1)
        send = QPushButton("Send")
        send.setObjectName("PrimaryButton")
        send.setIcon(self.ctx.icons.icon("send", 15, self.ctx.theme.palette.crust))
        send.clicked.connect(self.send_message)
        input_row.addWidget(send)
        chat_layout.addLayout(input_row)

        self.status_label = Muted(
            "DeskAI suggests commands but never runs them. You approve every execution."
        )
        chat_layout.addWidget(self.status_label)
        self.body_layout.addWidget(chat, 1)

        self._refresh_conversations()
        self._refresh_provider_state()

    # ------------------------------------------------------------------- state
    def _refresh_provider_state(self) -> None:
        provider = self.service.provider_name()
        model = str(self.ctx.config.get("ai.model", ""))
        self.provider_label.setText(f"{self.service.provider_label()} · {model or 'no model'}")
        if self.service.has_credentials():
            self.banner.hide()
        else:
            self.banner.show()
            self.banner_label.setText(
                f"{self.service.provider_label()} needs an API key before DeskAI can reply."
            )

    def _refresh_conversations(self) -> None:
        self.conversation_list.blockSignals(True)
        self.conversation_list.clear()
        for conversation in self.ctx.ai_history.conversations(30):
            label = str(conversation.get("title") or "Conversation")
            item = QListWidgetItem(self.ctx.icons.icon("ai", 15), label)
            item.setToolTip(
                f"{conversation.get('message_count', 0)} messages · "
                f"{relative_time(conversation.get('updated_at'))}"
            )
            item.setData(Qt.ItemDataRole.UserRole, int(conversation["id"]))
            self.conversation_list.addItem(item)
            if int(conversation["id"]) == self._conversation_id:
                self.conversation_list.setCurrentItem(item)
        self.conversation_list.blockSignals(False)

    def _on_conversation_selected(self, current, _previous) -> None:
        if current is None:
            return
        conversation_id = int(current.data(Qt.ItemDataRole.UserRole))
        if conversation_id == self._conversation_id:
            return
        self._conversation_id = conversation_id
        self._render_history()

    def new_conversation(self) -> None:
        self._conversation_id = self.service.new_conversation()
        self._render_history()
        self._refresh_conversations()
        self.input.setFocus()

    def _render_history(self) -> None:
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if self._conversation_id <= 0:
            self._add_placeholder()
            return
        messages = self.ctx.ai_history.messages(self._conversation_id)
        if not messages:
            self._add_placeholder()
            return
        for message in messages:
            bubble = MessageBubble(
                str(message["role"]),
                str(message["content"]),
                self.ctx.icons,
                self.ctx.theme,
                self._review_command,
            )
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
        QTimer.singleShot(30, self._scroll_to_bottom)

    def _add_placeholder(self) -> None:
        placeholder = Muted(
            "Ask about your system, explain a command, or use “Summarise logs” to make "
            "sense of the DeskOS log file."
        )
        placeholder.setWordWrap(True)
        self.messages_layout.insertWidget(0, placeholder)

    def _scroll_to_bottom(self) -> None:
        bar = self.messages_area.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ---------------------------------------------------------------- sending
    def send_message(self, text: str | None = None, extra_context: str = "") -> None:
        message = (text if text is not None else self.input.toPlainText()).strip()
        if not message:
            return
        if not self.service.has_credentials():
            self._open_settings()
            if not self.service.has_credentials():
                return
        self.input.clear()
        if self._conversation_id <= 0:
            self._conversation_id = self.service.new_conversation()
        bubble = MessageBubble("user", message, self.ctx.icons, self.ctx.theme)
        if self.messages_layout.count() > 0 and isinstance(
            self.messages_layout.itemAt(0).widget(), QLabel
        ):
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
        self._pending_label = Muted("DeskAI is thinking…")
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, self._pending_label)
        self._scroll_to_bottom()
        self.service.send(self._conversation_id, message, extra_context)

    def _explain_error(self) -> None:
        self.send_message(self.service.explain_error_prompt())

    def _summarize_logs(self) -> None:
        self.send_message(self.service.summarize_logs_prompt())

    def _on_started(self, conversation_id: int) -> None:
        self.status_label.setText("Waiting for the provider…")
        self._refresh_conversations()

    def _on_completed(self, conversation_id: int, reply: str) -> None:
        self.status_label.setText(
            "Reply received. DeskAI suggests commands but never runs them."
        )
        if conversation_id == self._conversation_id:
            self._render_history()
        self._refresh_conversations()

    def _on_failed(self, conversation_id: int, message: str) -> None:
        if self._pending_label is not None:
            self._pending_label.setText(f"Request failed: {message}")
            self._pending_label = None
        self.status_label.setText("The request failed — check the provider settings.")
        self._refresh_conversations()

    # --------------------------------------------------------------- commands
    def _review_command(self, command: str) -> None:
        answer = QMessageBox.question(
            self,
            "Run this command?",
            "DeskAI suggested the following command:\n\n"
            f"{command}\n\n"
            "It will be typed into DeskTerminal, where you still press Enter yourself. "
            "Only continue if you understand what it does.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        window = self.ctx.services["launcher"].open_builtin("app.terminal")
        if window is None:
            return
        page = getattr(window, "page", None)
        if page is not None and hasattr(page, "input"):
            page.input.setText(command)
            page.input.setFocus()
            self.ctx.toast("Command inserted into DeskTerminal — review it and press Enter")

    def _open_settings(self) -> None:
        dialog = ProviderDialog(self, self.service, self.ctx)
        if dialog.exec():
            self._refresh_provider_state()
            self.ctx.toast("DeskAI settings saved")
