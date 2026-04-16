from app.engine.simulation import new_simulation
from app.engine.colony import EngineColony
from app.engine import cycle


def test_simulation_emits_crop_matured_during_day_phase():
    sim = new_simulation(
        width=5, height=5, seed=42,
        colonies=[EngineColony(1, 'R', '#000', camp_x=0, camp_y=0, food_stock=18)],
        agents_per_colony=0,
    )
    t = None
    for row in sim.world.tiles:
        for tile in row:
            if tile.terrain == 'grass':
                t = tile
                t.terrain = 'grass'
                t.crop_state = 'growing'
                t.crop_growth_ticks = 59
                t.crop_colony_id = 1
                break
        if t: break
    assert t is not None

    while cycle.phase_for(sim.current_tick) != 'day':
        sim.step()
    events = sim.step()
    assert t.crop_state == 'mature'
    assert any(e['type'] == 'crop_matured' for e in events)


def test_simulation_dusk_phase_steps_agent_toward_camp():
    sim = new_simulation(
        width=5, height=5, seed=1,
        colonies=[EngineColony(1, 'R', '#000', camp_x=0, camp_y=0, food_stock=18)],
        agents_per_colony=1,
    )
    agent = sim.agents[0]
    agent.x, agent.y = 4, 4
    agent.colony_id = 1

    sim.current_tick = 60
    sim.step()
    assert (agent.x, agent.y) != (4, 4)
    assert abs(agent.x - 0) + abs(agent.y - 0) <= 7
