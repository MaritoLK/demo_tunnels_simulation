"""sim_lock: a module-level RLock with read()/write() context managers.

Both are re-entrant on the same thread (RLock); write excludes concurrent
reads and other writes. We only need one writer semantic here — a
full reader-writer lock is overkill for a single-worker deployment with
one tick loop thread."""
import threading
import time

from app.services import sim_lock


def test_write_excludes_concurrent_read():
    """If one thread holds write(), another thread entering read() blocks."""
    started = threading.Event()
    holding_write = threading.Event()
    observed = []

    def writer():
        with sim_lock.write():
            holding_write.set()
            time.sleep(0.1)
            observed.append('writer-done')

    def reader():
        started.set()
        with sim_lock.read():
            observed.append('reader-inside')

    holding_write.clear()
    tw = threading.Thread(target=writer)
    tw.start()
    holding_write.wait(1.0)
    assert holding_write.is_set()

    tr = threading.Thread(target=reader)
    tr.start()
    started.wait(1.0)
    tw.join(1.0)
    tr.join(1.0)

    # Writer must finish before reader enters.
    assert observed == ['writer-done', 'reader-inside']


def test_write_is_reentrant_on_same_thread():
    """A single thread that already holds write() can re-enter write()
    (e.g. a nested create_simulation call in tests). RLock semantics."""
    with sim_lock.write():
        with sim_lock.write():
            pass  # should not deadlock


def test_read_is_reentrant_on_same_thread():
    with sim_lock.read():
        with sim_lock.read():
            pass
