"""Background tick loop — unit tests for the per-iteration body.

The real loop is a threading.Thread that runs forever; that's untestable
directly. Instead the loop body factors into a pure function
`_single_tick(control_provider, stepper)` returning the seconds to sleep
next. Threading lives outside the tested path. This is the §9.23
"tick-rate / frame-rate decoupled by injecting the clock" pattern applied
to the service layer.
"""
import pytest

from app.services import tick_loop
from app.services.exceptions import SimulationNotFoundError


def _make_control(running, speed=1.0):
    return {'running': running, 'speed': speed}


def test_single_tick_skips_stepper_when_paused():
    calls = []
    interval = tick_loop._single_tick(
        control_provider=lambda: _make_control(running=False),
        stepper=lambda ticks=1: calls.append(ticks),
    )
    assert calls == []
    # Paused loops poll the control flag at a fixed interval — slow enough
    # that a paused sim produces ~no CPU load, fast enough that unpausing
    # feels instant to the user.
    assert interval == tick_loop.PAUSED_POLL_INTERVAL


def test_single_tick_calls_stepper_when_running():
    calls = []
    interval = tick_loop._single_tick(
        control_provider=lambda: _make_control(running=True, speed=2.0),
        stepper=lambda ticks=1: calls.append(ticks),
    )
    assert calls == [1]
    # speed=2 → 0.5s between ticks.
    assert interval == pytest.approx(0.5)


def test_single_tick_clamps_near_zero_speed():
    # If somehow speed gets past validation as ~0, avoid dividing by zero
    # and busy-looping. Floor is the service MIN_SPEED.
    calls = []
    interval = tick_loop._single_tick(
        control_provider=lambda: _make_control(running=True, speed=0.0),
        stepper=lambda ticks=1: calls.append(ticks),
    )
    assert calls == [1]
    assert interval > 0  # no division blow-up, no zero sleep


def test_single_tick_handles_missing_sim():
    # Fresh worker, no sim persisted yet: loop must not crash, must poll
    # at paused rate until a sim exists.
    calls = []

    def raise_not_found():
        raise SimulationNotFoundError('none')

    interval = tick_loop._single_tick(
        control_provider=raise_not_found,
        stepper=lambda ticks=1: calls.append(ticks),
    )
    assert calls == []
    assert interval == tick_loop.PAUSED_POLL_INTERVAL


def test_single_tick_swallows_stepper_errors():
    # A bug in engine code must not kill the loop thread. Caller logs,
    # returns paused interval so it backs off before retrying.
    def broken_stepper(ticks=1):
        raise RuntimeError('kaboom')

    interval = tick_loop._single_tick(
        control_provider=lambda: _make_control(running=True, speed=1.0),
        stepper=broken_stepper,
    )
    assert interval == tick_loop.PAUSED_POLL_INTERVAL


def test_single_tick_clamps_very_high_speed():
    # High speed → very small interval, but don't go below MIN_INTERVAL
    # (keeps the DB/step overhead under control even if a user sets speed=1000).
    interval = tick_loop._single_tick(
        control_provider=lambda: _make_control(running=True, speed=1000.0),
        stepper=lambda ticks=1: None,
    )
    assert interval >= tick_loop.MIN_INTERVAL
