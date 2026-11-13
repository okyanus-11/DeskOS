"""Background work helpers.

Anything that can block (application discovery, recursive file search, AI HTTP
requests, directory size calculation) runs through ``run_async`` so the Qt event
loop stays responsive.  Results are delivered on the main thread through
signals.
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

log = logging.getLogger(__name__)


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class AsyncWorker(QRunnable):
    def __init__(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:  # pragma: no cover - exercised indirectly
        try:
            result = self.function(*self.args, **self.kwargs)
        except Exception as exc:
            log.error("background task %s failed: %s", getattr(self.function, "__name__", "?"), exc)
            log.debug("%s", traceback.format_exc())
            self.signals.failed.emit(str(exc))
            return
        self.signals.finished.emit(result)


_pool = QThreadPool.globalInstance()
_active: set[AsyncWorker] = set()


def run_async(
    function: Callable[..., Any],
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[str], None] | None = None,
    *args: Any,
    **kwargs: Any,
) -> AsyncWorker:
    """Run ``function`` in the global thread pool and deliver its result."""
    worker = AsyncWorker(function, *args, **kwargs)
    _active.add(worker)

    def cleanup() -> None:
        _active.discard(worker)

    if on_done is not None:
        worker.signals.finished.connect(on_done)
    if on_error is not None:
        worker.signals.failed.connect(on_error)
    worker.signals.finished.connect(lambda _result: cleanup())
    worker.signals.failed.connect(lambda _message: cleanup())
    _pool.start(worker)
    return worker


def wait_for_all(milliseconds: int = 2000) -> bool:
    """Used during shutdown so background work does not outlive the app."""
    return _pool.waitForDone(milliseconds)
