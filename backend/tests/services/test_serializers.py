"""Tests for app.routes.serializers — wire-format correctness."""


def test_simulation_summary_includes_server_time_ms(app, db_session):
    """Snapshot must carry a monotonic server timestamp (ms) and the
    wall-clock ms at which the current tick was produced. The client
    uses these to place ticks on its own time axis."""
    del db_session  # fixture triggers TRUNCATE + cache reset; no direct use
    with app.app_context():
        from app.services import simulation_service
        from app.routes import serializers
        sim = simulation_service.create_simulation(
            width=4, height=4, seed=1, agent_count=1,
        )
        control = simulation_service.get_simulation_control()
        summary = serializers.simulation_summary(sim, control)
    assert 'server_time_ms' in summary
    assert 'tick_ms' in summary
    assert isinstance(summary['server_time_ms'], int)
    assert isinstance(summary['tick_ms'], int)
    assert summary['server_time_ms'] >= summary['tick_ms']
