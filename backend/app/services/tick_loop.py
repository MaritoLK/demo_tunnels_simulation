"""Background tick loop — drives the sim autonomously so the demo story is
'the colony is running' instead of 'click step to advance.'

Design (see STUDY_NOTES §9.27):
  * One daemon thread per worker. Single-worker deployment (§8.1) means
    exactly one tick loop globally — no distributed coordination needed.
  * Control flags (`running`, `speed`) live in the DB, not in the thread's
    memory. Routes PATCH the flags; the loop polls them each iteration.
    That keeps the source of truth durable and restart-safe.
  * The loop body is factored out as `_single_tick(control_provider, stepper)`
    so the decision logic is unit-testable without a real thread or DB.
    Threading is a thin shell around it.
  * Exceptions in stepper are logged and swallowed — a transient engine
    bug must not kill the loop (user would need to restart the worker
    to get ticks back). The loop backs off to paused-poll rate on error
    so it doesn't spin-log if the error is persistent.
"""
from __future__ import annotations

import logging
import threading

from flask import Flask

from app import db

from . import simulation_service
from .exceptions import SimulationNotFoundError


logger = logging.getLogger(__name__)

# Seconds to sleep when paused or when no sim exists. Short enough that
# unpausing feels instant; long enough that a paused sim burns no CPU.
PAUSED_POLL_INTERVAL = 0.2

# Lower bound on the inter-tick interval. Even if speed=1000, we cap the
# tick rate so DB commit overhead doesn't saturate the db container.
# 10ms ≈ 100 ticks/sec — plenty for a demo, well under commit cost.
MIN_INTERVAL = 0.01

_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _single_tick(control_provider, stepper):
    """One iteration of the tick loop. Returns seconds to sleep next.

    Pure-ish: no threading, no app context. Caller injects:
      control_provider: callable → {running, speed} dict, or raises
                         SimulationNotFoundError if no sim exists.
      stepper:           callable (ticks=1) → advances the sim one tick.

    Branches:
      * No sim → skip step, return paused interval.
      * Not running → skip step, return paused interval.
      * Running → step(1), return 1/speed (clamped).
      * Stepper raises → log, return paused interval (back off).
    """
    try:
        control = control_provider()
    except SimulationNotFoundError:
        return PAUSED_POLL_INTERVAL
    if not control['running']:
        return PAUSED_POLL_INTERVAL
    try:
        stepper(ticks=1)
    except Exception:
        logger.exception('tick_loop: step failed — backing off')
        return PAUSED_POLL_INTERVAL
    speed = max(control['speed'], simulation_service.MIN_SPEED)
    return max(MIN_INTERVAL, 1.0 / speed)


def _thread_body(app: Flask):
    """Long-running loop body. Pushes an app context per iteration so
    Flask-SQLAlchemy has access to the configured engine, and calls
    `db.session.remove()` after each iteration to return the connection
    to the pool (otherwise the thread would hold one connection forever,
    starving request handlers).
    """
    while not _stop_event.is_set():
        interval = PAUSED_POLL_INTERVAL
        try:
            with app.app_context():
                try:
                    interval = _single_tick(
                        control_provider=simulation_service.get_simulation_control,
                        stepper=simulation_service.step_simulation,
                    )
                finally:
                    db.session.remove()
        except Exception:
            logger.exception('tick_loop: iteration crashed')
        # _stop_event.wait doubles as a sleep AND a shutdown signal, so
        # stop() wakes the thread immediately instead of waiting a full
        # interval before noticing the flag.
        _stop_event.wait(interval)


def start(app: Flask):
    """Spawn the daemon thread. Idempotent — safe to call twice.

    daemon=True so the thread doesn't block interpreter shutdown. In a
    managed deployment you'd also want stop() called from a teardown
    hook, but for this demo's single-worker dev runner the daemon flag
    is enough.
    """
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(
        target=_thread_body, args=(app,), daemon=True, name='tick-loop',
    )
    _thread.start()


def stop(timeout: float = 2.0):
    """Signal the loop to exit and wait up to `timeout` seconds for it.

    Called from tests to avoid the thread mutating DB state between tests.
    Production doesn't need this (daemon=True handles interpreter exit),
    but a clean shutdown is cheap and lets us add tests later that assert
    'no thread is ticking when I don't want it to.'
    """
    global _thread
    _stop_event.set()
    if _thread is not None:
        _thread.join(timeout=timeout)
        _thread = None
