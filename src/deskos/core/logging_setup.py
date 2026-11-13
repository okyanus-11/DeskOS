"""Centralised logging configuration.

Every component logs through ``logging.getLogger(__name__)``; this module wires
those loggers to a rotating file in the user data directory and to stderr.  A
crash hook records uncaught exceptions so the bug-report flow can summarise
them.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import traceback
from collections.abc import Callable
from pathlib import Path

from deskos.core.paths import logs_dir

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
FILE_NAME = "deskos.log"
_configured = False
_exception_hook_callback: Callable[[str], None] | None = None


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> Path:
    """Configure root logging once and return the active log file path."""
    global _configured
    target = log_file or (logs_dir() / FILE_NAME)
    target.parent.mkdir(parents=True, exist_ok=True)

    if _configured:
        return target

    numeric = getattr(logging, str(level).upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(_LOG_FORMAT)
    file_handler = logging.handlers.RotatingFileHandler(
        target, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console = logging.StreamHandler(stream=sys.stderr)
    console.setFormatter(formatter)
    root.addHandler(console)

    logging.getLogger("deskos").info("logging initialised at %s", target)
    _configured = True
    return target


def get_log_path() -> Path:
    return logs_dir() / FILE_NAME


def tail_log(max_lines: int = 200) -> str:
    """Return the last ``max_lines`` of the log, used by DeskAI helpers."""
    path = get_log_path()
    if not path.is_file():
        return ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
    except OSError:
        return ""
    return "".join(lines[-max_lines:])


def set_exception_hook(callback: Callable[[str], None] | None) -> None:
    """Register a UI callback invoked with a formatted traceback."""
    global _exception_hook_callback
    _exception_hook_callback = callback


def install_exception_hook() -> None:
    previous = sys.excepthook

    def hook(exc_type, exc_value, exc_tb):  # type: ignore[no-untyped-def]
        if issubclass(exc_type, KeyboardInterrupt):
            previous(exc_type, exc_value, exc_tb)
            return
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.getLogger("deskos").critical("unhandled exception\n%s", text)
        if _exception_hook_callback is not None:
            try:
                _exception_hook_callback(text)
            except Exception:
                logging.getLogger("deskos").exception("exception hook failed")

    sys.excepthook = hook
