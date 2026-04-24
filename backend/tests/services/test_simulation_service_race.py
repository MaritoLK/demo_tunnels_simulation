"""Regression: PUT /simulation concurrent with a tick_loop iteration must
not leave the session with pending event rows that reference agent ids
from the pre-PUT sim. Reproduces the FK violation captured in
scripts/repro_put_race.py."""
import threading
import time

import pytest

from app.services import simulation_service


def _create_small_sim():
    return simulation_service.create_simulation(
        width=8, height=8, seed=1,
        colonies=2, agents_per_colony=2,
    )


def test_put_during_tick_does_not_raise_fk(app):
    with app.app_context():
        _create_small_sim()

    # Thread A: keeps stepping the sim.
    stop_stepper = threading.Event()
    stepper_errors = []

    def stepper():
        while not stop_stepper.is_set():
            try:
                with app.app_context():
                    simulation_service.step_simulation(ticks=1)
            except Exception as e:
                stepper_errors.append(e)
                return

    t = threading.Thread(target=stepper, daemon=True)
    t.start()
    time.sleep(0.2)  # let stepper run several ticks

    # Thread B (this thread): PUT a fresh sim.
    with app.app_context():
        _create_small_sim()

    stop_stepper.set()
    t.join(timeout=2.0)
    assert stepper_errors == [], (
        f'tick_loop crashed during concurrent PUT: {stepper_errors}'
    )
