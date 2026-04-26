"""Per-colony fog of war reveal + nightly reset.

Reveal is a 3×3 Chebyshev block around each non-rogue alive agent,
appended onto `colony.explored` after every step. Reset fires at the
dusk → night phase boundary so each new day starts dark again — the
mechanism that gives exploration a stake instead of being a one-time
tax.
"""
from app.engine import config, cycle
from app.engine.colony import EngineColony
from app.engine.simulation import Simulation
from app.engine.world import Tile, World


def _solid_grass_world(width=10, height=10):
    """Build a world bypassing generate() so the fog tests don't depend
    on biome-roll randomness — every tile is grass, no resources, no
    crops. Keeps the assertions about explored coords trivially exact."""
    w = World(width, height)
    w.tiles = [
        [Tile(x, y, 'grass') for x in range(width)]
        for y in range(height)
    ]
    return w


def _colony(camp_x=2, camp_y=2, name='Red'):
    return EngineColony(
        id=1, name=name, color='#e74c3c',
        camp_x=camp_x, camp_y=camp_y, food_stock=0,
    )


def _sim_with_one_agent(*, agent_x, agent_y, rogue=False, colony=None):
    if colony is None:
        colony = _colony()
    sim = Simulation(_solid_grass_world(), colonies=[colony])
    # Manually inject one agent at a known position so we don't depend on
    # spawn RNG. Foreground field copies mirror new_simulation's defaults.
    from app.engine.agent import Agent
    a = Agent(name='scout', x=agent_x, y=agent_y, agent_id=1, colony_id=colony.id)
    a.rogue = rogue
    sim.agents.append(a)
    return sim, colony, a


def test_step_reveals_3x3_around_alive_agent():
    sim, colony, _agent = _sim_with_one_agent(agent_x=4, agent_y=4)
    sim.step()
    expected = {(x, y) for x in range(3, 6) for y in range(3, 6)}
    assert expected.issubset(colony.explored), (
        f'expected 3x3 reveal centred on (4,4); got {sorted(colony.explored)}'
    )
    # And nothing outside the radius
    extras = colony.explored - expected
    assert not extras, f'reveal leaked outside radius: {sorted(extras)}'


def test_reveal_clamps_to_world_bounds():
    # Agent at the corner — bottom and right rows of the 3x3 are out of
    # bounds and must not be added.
    sim, colony, _agent = _sim_with_one_agent(agent_x=0, agent_y=0)
    sim.step()
    expected = {(0, 0), (0, 1), (1, 0), (1, 1)}
    assert colony.explored == expected, (
        f'expected only in-bounds quadrant; got {sorted(colony.explored)}'
    )


def test_rogue_agents_do_not_contribute_to_fog():
    sim, colony, _agent = _sim_with_one_agent(agent_x=4, agent_y=4, rogue=True)
    sim.step()
    assert colony.explored == set(), (
        'rogue agents have no colony tie and must not paint colony fog'
    )


def test_dusk_to_night_clears_explored():
    # Set current_tick = first night tick. step() reads phase_for(now) =
    # 'night' and phase_for(now - 1) = 'dusk' → reset fires before the
    # tick's reveal repaints around (4,4). Assertion: only the new
    # reveal survives, none of the pre-seeded leftovers do.
    sim, colony, _agent = _sim_with_one_agent(agent_x=4, agent_y=4)
    sim.current_tick = cycle.PHASES.index('night') * cycle.TICKS_PER_PHASE
    assert cycle.phase_for(sim.current_tick) == 'night'
    assert cycle.phase_for(sim.current_tick - 1) == 'dusk'
    colony.explored.update({(0, 0), (9, 9), (5, 5)})
    sim.step()
    assert (0, 0) not in colony.explored
    assert (9, 9) not in colony.explored
    expected = {(x, y) for x in range(3, 6) for y in range(3, 6)}
    assert colony.explored == expected


def test_other_phase_transitions_do_not_clear_explored():
    # Day → dusk crossing: stale fog must NOT wipe, only dusk → night
    # does. Set current_tick = first dusk tick so step() sees the
    # day → dusk boundary.
    sim, colony, _agent = _sim_with_one_agent(agent_x=4, agent_y=4)
    sim.current_tick = cycle.PHASES.index('dusk') * cycle.TICKS_PER_PHASE
    assert cycle.phase_for(sim.current_tick) == 'dusk'
    assert cycle.phase_for(sim.current_tick - 1) == 'day'
    colony.explored.add((9, 9))
    sim.step()
    assert (9, 9) in colony.explored, (
        'day → dusk must not wipe fog; only dusk → night does'
    )


def test_reveal_radius_constant_drives_size():
    # Pin the relationship between REVEAL_RADIUS and the reveal area so
    # the upcoming walk-skill upgrade (radius 1 → 2 → 3) won't silently
    # break with hardcoded loop bounds.
    assert config.REVEAL_RADIUS == 1
    sim, colony, _agent = _sim_with_one_agent(agent_x=5, agent_y=5)
    sim.step()
    side = 2 * config.REVEAL_RADIUS + 1
    assert len(colony.explored) == side * side
