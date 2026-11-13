"""A tiny synchronous event bus.

The core layer deliberately avoids importing Qt so that configuration,
persistence and plugin loading can be unit-tested without a GUI.  UI code
subscribes to the bus to stay in sync (theme changes, config edits, workspace
switches, plugin reloads).
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

Handler = Callable[..., None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, topic: str, handler: Handler) -> Callable[[], None]:
        """Register ``handler``; returns a callable that unsubscribes it."""
        with self._lock:
            self._handlers[topic].append(handler)

        def unsubscribe() -> None:
            with self._lock:
                if handler in self._handlers.get(topic, []):
                    self._handlers[topic].remove(handler)

        return unsubscribe

    def emit(self, topic: str, **payload: Any) -> None:
        with self._lock:
            handlers = list(self._handlers.get(topic, ()))
        for handler in handlers:
            try:
                handler(**payload)
            except Exception:  # a broken subscriber must not break the emitter
                log.exception("event handler for %r failed", topic)

    def clear(self) -> None:
        with self._lock:
            self._handlers.clear()
