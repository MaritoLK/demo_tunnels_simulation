"""Single source of truth for serializing sim-mutating requests against
the background tick loop.

Problem this solves:
  PUT /simulation wipes (`DELETE FROM agents`) and rebuilds the sim. If
  the tick loop is mid-tick with the old in-memory Simulation object,
  its ORM session has pending Event rows referencing old `agent.id`s.
  The PUT commits the DELETE before the tick loop's autoflush runs;
  autoflush then INSERTs events with stale agent_ids → FK violation →
  5 consecutive failures → auto-pause. See scripts/repro_put_race.py.

Why an RLock and not a ReadWriteLock:
  We have one writer (PUT) and one reader (tick_loop thread). Under that
  shape a plain RLock used with `write()` always and `read()` never
  concurrent with `write()` is functionally correct and trivial to
  reason about. Upgrading to a proper RW lock is a 5-line change if a
  second reader ever appears.

Re-entrancy matters: `create_simulation` may call itself (tests) or be
called from a handler that has already acquired write() — RLock lets
that work instead of deadlocking.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager

_lock = threading.RLock()


@contextmanager
def read():
    """Acquire for read. Blocks if a writer holds the lock."""
    _lock.acquire()
    try:
        yield
    finally:
        _lock.release()


@contextmanager
def write():
    """Acquire for write. Excludes concurrent readers AND other writers."""
    _lock.acquire()
    try:
        yield
    finally:
        _lock.release()
