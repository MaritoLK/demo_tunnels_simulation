from app.engine.agent import Agent


def test_agent_has_colony_id_and_dawn_flag():
    a = Agent(name='A', x=0, y=0, colony_id=7)
    assert a.colony_id == 7
    assert a.ate_this_dawn is False


def test_agent_colony_id_defaults_to_none():
    a = Agent(name='A', x=0, y=0)
    assert a.colony_id is None
