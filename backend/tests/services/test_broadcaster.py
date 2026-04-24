"""Broadcaster: fan-out pub-sub inside a single process."""
import queue
import threading
import time

from app.services import broadcaster


def test_subscribe_receives_publish():
    q = broadcaster.subscribe()
    try:
        broadcaster.publish({'tick': 1})
        msg = q.get(timeout=1.0)
        assert msg == {'tick': 1}
    finally:
        broadcaster.unsubscribe(q)


def test_multiple_subscribers_each_get_copy():
    q1 = broadcaster.subscribe()
    q2 = broadcaster.subscribe()
    try:
        broadcaster.publish({'tick': 5})
        assert q1.get(timeout=1.0) == {'tick': 5}
        assert q2.get(timeout=1.0) == {'tick': 5}
    finally:
        broadcaster.unsubscribe(q1)
        broadcaster.unsubscribe(q2)


def test_slow_subscriber_does_not_block_publisher():
    """If a subscriber's queue hits its bound, the publisher drops the
    message for that subscriber rather than blocking. We never want one
    dead browser tab to freeze the tick loop."""
    q = broadcaster.subscribe(maxsize=2)
    try:
        broadcaster.publish({'n': 1})
        broadcaster.publish({'n': 2})
        # Third publish finds q full. Must not block.
        t0 = time.monotonic()
        broadcaster.publish({'n': 3})
        assert time.monotonic() - t0 < 0.2, 'publish blocked waiting for slow subscriber'
    finally:
        broadcaster.unsubscribe(q)


def test_unsubscribe_stops_delivery():
    q = broadcaster.subscribe()
    broadcaster.unsubscribe(q)
    broadcaster.publish({'n': 1})
    assert q.empty()
