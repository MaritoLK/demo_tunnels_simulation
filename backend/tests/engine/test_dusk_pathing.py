import pytest

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
                t.crop_state = 'growing'
                t.crop_growth_ticks = 59
                t.crop_colony_id = 1
                break
        if t: break
    assert t is not None

    # Bounded advance to next 'day' phase. Unbounded while-loop hangs the
    # suite if phase_for ever regresses — pytest.fail surfaces the bug.
    for _ in range(cycle.TICKS_PER_DAY):
        if cycle.phase_for(sim.current_tick) == 'day':
            break
        sim.step()
    else:
        pytest.fail('phase_for never reached day within one full cycle')
    events = sim.step()
    assert t.crop_state == 'mature'
    assert any(e['type'] == 'crop_matured' for e in events)


def test_simulation_dusk_phase_steps_agent_toward_camp():
    # Bigger world so the agent can sit BEYOND the plant ring (Chebyshev
    # > 4 from camp) — otherwise the plant rung pins them on an empty
    # grass tile and the dusk-movement assertion misfires. Position
    # picked deliberately at distance 8 (camp at (0,0), agent at (8,8))
    # so neither plant nor opportunistic gather can fire there.
    sim = new_simulation(
        width=10, height=10, seed=1,
        colonies=[EngineColony(1, 'R', '#000', camp_x=0, camp_y=0, food_stock=18)],
        agents_per_colony=1,
    )
    agent = sim.agents[0]
    agent.x, agent.y = 8, 8
    agent.colony_id = 1
    # Clear any resource on the agent's tile so the opportunistic
    # wood/stone gather rung doesn't pin them in place — this test
    # is about dusk-phase MOVEMENT, not 'do anything productive'.
    here = sim.world.get_tile(8, 8)
    here.terrain = 'grass'
    here.resource_type = None
    here.resource_amount = 0.0

    # Warp to the start of dusk. Derived from cycle constants so phase-order
    # tweaks don't silently land the test in a non-dusk phase.
    sim.current_tick = cycle.PHASES.index('dusk') * cycle.TICKS_PER_PHASE
    sim.step()
    assert (agent.x, agent.y) != (8, 8)
