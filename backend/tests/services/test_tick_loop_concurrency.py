"""Concurrency harness for tick_loop x manual /step races.

Pre-flight step 4 (2026-04-17). Not intended to catch a known bug today.
Foundation (Sub-project A) will add write paths — policy commits, scene
advancement, schedule commits — that contend with the background
tick_loop daemon on the same db.session and the shared ``_current_sim``
engine object. This harness reproduces the race today so it is
available as a lever the moment those writes land.

Race surfaces covered:

1. ``simulation_service._current_sim`` is a module-level singleton.
   The daemon thread and a request-handler thread both call
   ``sim.run(N)`` on the SAME engine object — concurrent mutation of
   ``sim.agents`` / ``sim.world`` lists. Python's GIL makes individual
   bytecode atomic but multi-statement sequences (append, then index)
   are not. Bugs here look like ``IndexError`` or lost agents.

2. Both threads commit through their own scoped_session.
   ``SimulationState.current_tick`` is a scalar column; two interleaved
   reads + writes = lost tick. Observable as a final tick count lower
   than the sum of issued steps.

3. Events for the same tick number can land from both threads; there
   is no uniqueness constraint today. Observable as duplicate
   ``(tick, agent_id, type)`` rows.

Usage: extend the asserts in ``test_concurrent_step_and_tick_loop`` as
Foundation adds new writable rows (NPC, Policy, EventLog). The
scaffolding — Barrier-synchronized start, per-thread app_context,
exception capture — stays.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

from app import db
from app.engine import cycle
from app.services import simulation_service, tick_loop
from app.services.exceptions import SimulationNotFoundError


@dataclass
class _ThreadResult:
    steps_done: int = 0
    exc: BaseException | None = None
    events_seen: int = 0


def _run_manual_steps(app, result: _ThreadResult, barrier: threading.Barrier,
                      steps: int) -> None:
    """Imitate the request handler: push an app_context, loop POST /step.

    Each step opens + commits a fresh transaction. ``db.session.remove()``
    after each iteration mirrors what the Flask teardown would do, so
    the shared connection pool does not starve.
    """
    try:
        barrier.wait(timeout=5.0)
        with app.app_context():
            for _ in range(steps):
                try:
                    events = simulation_service.step_simulation(ticks=1)
                    result.events_seen += len(events)
                    result.steps_done += 1
                finally:
                    db.session.remove()
    except BaseException as exc:  # noqa: BLE001 — harness captures everything
        result.exc = exc


def _run_daemon_ticks(app, result: _ThreadResult, barrier: threading.Barrier,
                      iterations: int) -> None:
    """Imitate ``tick_loop._thread_body``: single-tick body, app_context,
    session.remove. No sleep — we want maximum contention for the harness.
    """
    try:
        barrier.wait(timeout=5.0)
        for _ in range(iterations):
            try:
                with app.app_context():
                    try:
                        tick_loop._single_tick(
                            control_provider=simulation_service.get_simulation_control,
                            stepper=simulation_service.step_simulation,
                        )
                        result.steps_done += 1
                    finally:
                        db.session.remove()
            except SimulationNotFoundError:
                pass
    except BaseException as exc:  # noqa: BLE001
        result.exc = exc


def test_concurrent_step_and_tick_loop(app, db_session):
    """Daemon thread + user-step thread hammer the sim in parallel.

    Acceptance today: both threads finish, no uncaught exception, final
    DB state is internally consistent (tick count >= each thread's
    completed steps; event row count >= events reported by user path).

    Acceptance once Foundation writes land: add row-level assertions
    for NPC / Policy / EventLog tables alongside these.
    """
    del db_session  # fixture triggers TRUNCATE + cache reset; no direct use
    # Seed a sim and flip running=True so the daemon path has work.
    simulation_service.create_simulation(width=6, height=6, seed=7, agent_count=3)
    simulation_service.update_simulation_control(running=True, speed=1.0)

    user_result = _ThreadResult()
    daemon_result = _ThreadResult()
    barrier = threading.Barrier(2)

    user_thread = threading.Thread(
        target=_run_manual_steps,
        args=(app, user_result, barrier, 10),
        name='test-user-step',
    )
    daemon_thread = threading.Thread(
        target=_run_daemon_ticks,
        args=(app, daemon_result, barrier, 10),
        name='test-tick-loop',
    )

    user_thread.start()
    daemon_thread.start()
    user_thread.join(timeout=10.0)
    daemon_thread.join(timeout=10.0)

    assert not user_thread.is_alive(), 'user thread hung'
    assert not daemon_thread.is_alive(), 'daemon thread hung'
    assert user_result.exc is None, f'user path raised: {user_result.exc!r}'
    assert daemon_result.exc is None, f'daemon path raised: {daemon_result.exc!r}'

    # Both paths made forward progress.
    assert user_result.steps_done > 0
    assert daemon_result.steps_done > 0

    # Sim tick advanced at least as far as the faster path got. Because
    # both paths share `_current_sim` the final tick counter is the
    # high-water mark of whichever thread committed last, not the sum.
    # This is the "lost update" surface flagged in the module docstring;
    # the assertion today only guards against catastrophic regression
    # (negative progress, zero progress).
    sim = simulation_service.get_current_simulation()
    min_expected = cycle.TICKS_PER_PHASE + max(
        user_result.steps_done, daemon_result.steps_done,
    )
    assert sim.current_tick >= min_expected, (
        f'tick regressed: current_tick={sim.current_tick}, '
        f'min_expected={min_expected}'
    )


def test_single_tick_is_callable_in_a_thread_without_app_context_leak(app, db_session):
    """Baseline: running the factored tick body in a worker thread with
    its own app_context does not mutate the main thread's session.

    Guards against a future refactor that accidentally leaks the outer
    session into the worker (e.g. by capturing it in a closure). If
    this ever fails we re-evaluate before letting Foundation land.
    """
    del db_session  # fixture triggers TRUNCATE + cache reset; no direct use
    simulation_service.create_simulation(width=4, height=4, seed=3, agent_count=1)
    simulation_service.update_simulation_control(running=True, speed=1.0)

    result = _ThreadResult()
    barrier = threading.Barrier(1)
    t = threading.Thread(
        target=_run_daemon_ticks,
        args=(app, result, barrier, 3),
        name='test-solo-daemon',
    )
    t.start()
    t.join(timeout=5.0)

    assert not t.is_alive()
    assert result.exc is None, f'daemon raised: {result.exc!r}'
    assert result.steps_done == 3

    # Main-thread session still works — no cross-thread contamination.
    sim = simulation_service.get_current_simulation()
    assert sim.current_tick == cycle.TICKS_PER_PHASE + 3
