"""Each successful tick pushes one snapshot onto the broadcaster."""
from app.services import broadcaster, tick_loop


def test_single_tick_publishes_one_payload(app, db_session, monkeypatch):
    """After a successful stepper call, _single_tick publishes exactly
    one snapshot with the post-tick state."""
    del db_session  # fixture triggers TRUNCATE + cache reset; no direct use
    payloads = []
    real_publish = broadcaster.publish

    def capture_and_publish(payload):
        payloads.append(payload)
        real_publish(payload)

    monkeypatch.setattr(broadcaster, 'publish', capture_and_publish)

    with app.app_context():
        from app.services import simulation_service
        simulation_service.create_simulation(
            width=4, height=4, seed=1, agent_count=1,
        )
        simulation_service.update_simulation_control(running=True, speed=1.0)
        tick_loop._single_tick(
            control_provider=simulation_service.get_simulation_control,
            stepper=simulation_service.step_simulation,
            pause_on_fatal=lambda: None,
        )
    assert len(payloads) == 1
    assert 'sim' in payloads[0]
    assert 'agents' in payloads[0]
    assert payloads[0]['sim']['server_time_ms'] > 0


def test_tick_failure_does_not_publish(app, db_session, monkeypatch):
    del db_session
    payloads = []
    monkeypatch.setattr(broadcaster, 'publish', payloads.append)

    def fail(**_kw):
        raise RuntimeError('boom')

    with app.app_context():
        from app.services import simulation_service
        simulation_service.create_simulation(
            width=4, height=4, seed=1, agent_count=1,
        )
        simulation_service.update_simulation_control(running=True, speed=1.0)
        tick_loop._single_tick(
            control_provider=simulation_service.get_simulation_control,
            stepper=fail,
            pause_on_fatal=lambda: None,
        )
    assert payloads == []
