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


def test_single_tick_speeds_up_during_night(monkeypatch):
    # Auto-speedup: the wall-clock interval shrinks by NIGHT_SPEEDUP_MULT
    # when the sim sits in the night phase. Engine ticks are unchanged —
    # same RNG draws, same decay, same events — so determinism + the
    # `speed` control's role as source of truth are both preserved.
    # The speedup is purely a UX knob so the user doesn't stare at
    # sleeping agents at default speed.
    from app.engine import cycle
    from app.services import simulation_service

    class _FakeSim:
        # First tick of the night phase. Broadcast payload-build will
        # throw on this stub (no agents/world/etc.), but the speedup
        # decision is captured before that — exactly the resilience
        # contract we want: a broadcast failure must not undo the
        # phase-speedup signal that already fired.
        current_tick = cycle.PHASES.index('night') * cycle.TICKS_PER_PHASE

    monkeypatch.setattr(
        simulation_service, 'get_current_simulation',
        lambda: _FakeSim(),
    )

    interval = tick_loop._single_tick(
        control_provider=lambda: _make_control(running=True, speed=1.0),
        stepper=lambda ticks=1: None,
    )
    # speed=1 → base interval 1.0. Night divides by NIGHT_SPEEDUP_MULT.
    assert interval == pytest.approx(1.0 / tick_loop.NIGHT_SPEEDUP_MULT)


def test_single_tick_no_speedup_outside_night(monkeypatch):
    # Symmetric guard: dawn / day / dusk all use the user's chosen speed
    # unmodified. Without this assertion, a regression that always
    # divided by the multiplier would still pass the night test.
    from app.engine import cycle
    from app.services import simulation_service

    class _FakeSim:
        current_tick = cycle.PHASES.index('day') * cycle.TICKS_PER_PHASE

    monkeypatch.setattr(
        simulation_service, 'get_current_simulation',
        lambda: _FakeSim(),
    )

    interval = tick_loop._single_tick(
        control_provider=lambda: _make_control(running=True, speed=1.0),
        stepper=lambda ticks=1: None,
    )
    assert interval == pytest.approx(1.0)


def test_single_tick_speedup_respects_min_interval(monkeypatch):
    # Even the night divisor cannot drag interval below MIN_INTERVAL —
    # at high user speeds the floor still wins so DB commit overhead
    # stays bounded.
    from app.engine import cycle
    from app.services import simulation_service

    class _FakeSim:
        current_tick = cycle.PHASES.index('night') * cycle.TICKS_PER_PHASE

    monkeypatch.setattr(
        simulation_service, 'get_current_simulation',
        lambda: _FakeSim(),
    )

    interval = tick_loop._single_tick(
        control_provider=lambda: _make_control(running=True, speed=1000.0),
        stepper=lambda ticks=1: None,
    )
    assert interval >= tick_loop.MIN_INTERVAL


def test_single_tick_no_speedup_when_sim_fetch_fails(monkeypatch):
    # If the broadcast block can't read the sim (transient DB blip,
    # cache miss right after a fresh deploy), the speedup must NOT
    # fire — we don't know the phase, so we fall back to the user's
    # chosen interval rather than guessing wrong direction.
    from app.services import simulation_service

    def _raise(*_a, **_kw):
        raise simulation_service.SimulationNotFoundError('none')

    monkeypatch.setattr(
        simulation_service, 'get_current_simulation', _raise,
    )

    interval = tick_loop._single_tick(
        control_provider=lambda: _make_control(running=True, speed=1.0),
        stepper=lambda ticks=1: None,
    )
    assert interval == pytest.approx(1.0)
