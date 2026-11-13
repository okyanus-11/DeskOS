"""DeskTerminal: a real shell process driven through pipes.

This is not a terminal emulator: DeskOS spawns the actual shell executable,
streams its stdout/stderr, and forwards typed commands on stdin.  Full-screen
console programs (vim, top, interactive installers) require a real TTY and are
therefore opened in the native terminal via the toolbar button instead — that
limitation is reported to the user rather than faked.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt
from PySide6.QtGui import QFont, QFontDatabase, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from deskos.applications.base import AppPage
from deskos.platform.base import LaunchError, ShellSpec
from deskos.ui.components import Muted, IconButton

log = logging.getLogger(__name__)

ANSI_PATTERN = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean_output(text: str) -> str:
    """Strip ANSI escapes and control characters from shell output."""
    text = ANSI_PATTERN.sub("", text)
    text = CONTROL_PATTERN.sub("", text)
    return text.replace("\r\n", "\n").replace("\r", "\n")


class TerminalPage(AppPage):
    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(context, parent)
        self._process: QProcess | None = None
        self._shells: list[ShellSpec] = []
        self._history: list[str] = []
        self._stopping = False
        self._history_index = 0
        self._cwd = self.ctx.platform.files.default_path()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 6, 18, 16)
        root.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self.shell_combo = QComboBox()
        self.shell_combo.setMinimumWidth(190)
        self.shell_combo.currentIndexChanged.connect(self._on_shell_changed)
        toolbar.addWidget(self.shell_combo)

        self.external_button = QPushButton("Open native terminal")
        self.external_button.setIcon(self.icons.icon("external", 15))
        self.external_button.setToolTip(
            "Open this shell in its own terminal window for full TTY support"
        )
        self.external_button.clicked.connect(self._launch_external)
        toolbar.addWidget(self.external_button)

        pick_folder = IconButton(self.icons, "folder", "Start in another folder", 30, 16)
        pick_folder.clicked.connect(self._pick_directory)
        toolbar.addWidget(pick_folder)

        toolbar.addStretch(1)
        self.state_label = Muted("")
        toolbar.addWidget(self.state_label)
        clear_button = IconButton(self.icons, "trash", "Clear output", 30, 16)
        clear_button.clicked.connect(lambda: self.output.clear())
        toolbar.addWidget(clear_button)
        restart_button = IconButton(self.icons, "refresh", "Restart shell", 30, 16)
        restart_button.clicked.connect(self.restart_shell)
        toolbar.addWidget(restart_button)
        root.addLayout(toolbar)

        self.cwd_label = Muted(self._cwd)
        root.addWidget(self.cwd_label)

        self.output = QPlainTextEdit()
        self.output.setObjectName("TerminalOutput")
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        fixed = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        fixed.setPointSize(max(9, int(10 * self.theme.scale)))
        self.output.setFont(fixed)
        self.output.setMinimumHeight(320)
        root.addWidget(self.output, 1)

        prompt_row = QHBoxLayout()
        prompt_row.setSpacing(8)
        self.prompt_label = QLabel("❯")
        self.prompt_label.setObjectName("Accent")
        prompt_row.addWidget(self.prompt_label)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a command and press Enter…")
        self.input.setFont(fixed)
        self.input.returnPressed.connect(self._submit)
        self.input.installEventFilter(self)
        prompt_row.addWidget(self.input, 1)
        run_button = QPushButton("Run")
        run_button.setObjectName("PrimaryButton")
        run_button.clicked.connect(self._submit)
        prompt_row.addWidget(run_button)
        root.addLayout(prompt_row)

        self.hint = Muted(
            "Commands execute in a real shell subprocess. Full-screen console apps need the "
            "native terminal button."
        )
        root.addWidget(self.hint)

        self._load_shells()

    # ------------------------------------------------------------------ shells
    def _load_shells(self) -> None:
        try:
            self._shells = [
                shell
                for shell in self.ctx.platform.terminal.available_shells()
                if not shell.is_external_only
            ]
        except Exception:
            log.exception("shell discovery failed")
            self._shells = []
        self.shell_combo.blockSignals(True)
        self.shell_combo.clear()
        for shell in self._shells:
            self.shell_combo.addItem(shell.label, shell.id)
        self.shell_combo.blockSignals(False)
        if not self._shells:
            self.state_label.setText("No shell found")
            self.append_text(
                "No PowerShell, cmd or POSIX shell was found on this system.\n"
                "DeskTerminal needs one of these to be installed.\n"
            )
            self.input.setEnabled(False)
            return
        self.start_shell(self._shells[0])

    def current_shell(self) -> ShellSpec | None:
        index = self.shell_combo.currentIndex()
        if 0 <= index < len(self._shells):
            return self._shells[index]
        return self._shells[0] if self._shells else None

    def start_shell(self, shell: ShellSpec) -> None:
        self.stop_shell()
        self.output.clear()
        self.append_text(f"DeskOS terminal — {shell.label} ({shell.executable})\n")
        self.append_text(f"Working directory: {self._cwd}\n\n")
        process = QProcess(self)
        process.setWorkingDirectory(self._cwd)
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("TERM", "dumb")
        environment.insert("NO_COLOR", "1")
        process.setProcessEnvironment(environment)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)
        self._process = process
        try:
            process.start(shell.executable, shell.repl_args)
        except Exception as exc:
            log.exception("could not start shell")
            self.append_text(f"Failed to start {shell.label}: {exc}\n")
            self.state_label.setText("Shell failed to start")
            return
        if not process.waitForStarted(4000):
            self.append_text(f"{shell.label} did not start in time.\n")
            self.state_label.setText("Shell failed to start")
            return
        self.state_label.setText("Shell running")
        self.input.setFocus()

    def restart_shell(self) -> None:
        shell = self.current_shell()
        if shell is not None:
            self.start_shell(shell)

    def stop_shell(self) -> None:
        self._stopping = True
        if self._process is None:
            return
        process = self._process
        self._process = None
        try:
            process.closeWriteChannel()
            if process.state() != QProcess.ProcessState.NotRunning:
                process.terminate()
                if not process.waitForFinished(800):
                    process.kill()
                    process.waitForFinished(400)
        except Exception:
            log.debug("error while stopping shell", exc_info=True)
        self.state_label.setText("Shell stopped")

    def _on_shell_changed(self, _index: int) -> None:
        shell = self.current_shell()
        if shell is not None:
            self.start_shell(shell)

    def _pick_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Start shell in", self._cwd)
        if directory:
            self._cwd = directory
            self.cwd_label.setText(directory)
            self.restart_shell()

    # ------------------------------------------------------------------- io
    def _read_stdout(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardOutput().data()).decode(
            "utf-8", errors="replace"
        )
        self.append_text(clean_output(data))

    def _read_stderr(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardError().data()).decode(
            "utf-8", errors="replace"
        )
        text = clean_output(data)
        if text.strip():
            self.append_text(text, error=True)

    def append_text(self, text: str, *, error: bool = False) -> None:
        if not text:
            return
        color = self.theme.palette.accents["red"] if error else self.theme.palette.text
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        prefix = "" if error else ""
        safe = (prefix + text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe = safe.replace("\n", "<br>")
        cursor.insertHtml(f'<span style="color:{color};white-space:pre">{safe}</span>')
        self.output.setTextCursor(cursor)
        self.output.ensureCursorVisible()

    def _submit(self) -> None:
        command = self.input.text()
        if not command.strip():
            return
        self.input.clear()
        self._history.append(command)
        self._history_index = len(self._history)
        self.append_text(f"❯ {command}\n")
        self.send_command(command)

    def send_command(self, command: str) -> None:
        """Send a command to the running shell (used by DeskAI after approval)."""
        if self._process is None or self._process.state() == QProcess.ProcessState.NotRunning:
            self.append_text("No shell process is running.\n", error=True)
            return
        payload = command + ("\r\n" if os.name == "nt" else "\n")
        self._process.write(payload.encode("utf-8"))
        self._process.waitForBytesWritten(500)

    def _on_finished(self, exit_code: int, _status) -> None:
        self.append_text(f"\n[shell exited with code {exit_code}]\n", error=exit_code != 0)
        self.state_label.setText(f"Exited ({exit_code})")

    def _on_error(self, error) -> None:
        if self._stopping:
            log.debug("shell ended while stopping: %s", error)
            return
        log.warning("terminal process error: %s", error)
        self.append_text(f"[terminal error: {error}]\n", error=True)

    # ---------------------------------------------------------------- events
    def eventFilter(self, watched, event) -> None:  # noqa: N802
        if watched is self.input and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Up:
                if self._history:
                    self._history_index = max(0, self._history_index - 1)
                    self.input.setText(self._history[self._history_index])
                return True
            if event.key() == Qt.Key.Key_Down:
                if self._history:
                    self._history_index = min(len(self._history), self._history_index + 1)
                    self.input.setText(
                        self._history[self._history_index]
                        if self._history_index < len(self._history)
                        else ""
                    )
                return True
        return super().eventFilter(watched, event)

    def _launch_external(self) -> None:
        shell = self.current_shell()
        if shell is None:
            return
        try:
            self.ctx.platform.terminal.launch_external(shell, self._cwd)
        except LaunchError as exc:
            self.ctx.toast(str(exc))

    def on_closing(self) -> None:
        self.stop_shell()
