"""In-process pub-sub for tick snapshots.

One publisher (the tick loop) fans out to N subscribers (one per live
SSE connection). Bounded queue per subscriber: if a client tab is
backgrounded or stalls, the publisher drops that subscriber's message
instead of blocking the tick loop. Single-worker deployment (§8.1)
means no cross-process broadcast needed — a simple list of queues is
the whole implementation.
"""
from __future__ import annotations

import queue
import threading
from typing import Any

_subscribers_lock = threading.Lock()
_subscribers: list[queue.Queue[Any]] = []


def subscribe(maxsize: int = 8) -> queue.Queue:
    """Register a new subscriber. Returned queue receives every
    subsequent publish. Caller is responsible for calling unsubscribe()
    when done (typically in a finally clause of a stream handler)."""
    q: queue.Queue = queue.Queue(maxsize=maxsize)
    with _subscribers_lock:
        _subscribers.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _subscribers_lock:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def publish(payload: Any) -> None:
    """Fan out payload to every subscriber. A full queue drops the
    message for that subscriber; the next publish will catch them up.
    Never blocks."""
    with _subscribers_lock:
        snapshot = list(_subscribers)
    for q in snapshot:
        try:
            q.put_nowait(payload)
        except queue.Full:
            pass
