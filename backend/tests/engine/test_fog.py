"""Per-colony fog of war reveal.

Reveal is a 3×3 Chebyshev block around each non-rogue alive agent,
appended onto `colony.explored` after every step. The set persists
across phase boundaries — once a colony has scouted a tile it stays
on the map for the lifetime of the run.
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
    # Reveal logic isolated from agent decision-making: a full sim.step
    # would push the agent through decide_action, which now might pick
    # 'explore' on the same tick (plant gate is radius-bounded), moving
    # the agent and shifting the reveal centre. Calling _refresh_fog
    # directly pins the radius pass without coupling to action choice.
    sim, colony, agent = _sim_with_one_agent(agent_x=4, agent_y=4)
    sim._refresh_fog([agent])
    expected = {(x, y) for x in range(3, 6) for y in range(3, 6)}
    assert expected.issubset(colony.explored), (
        f'expected 3x3 reveal centred on (4,4); got {sorted(colony.explored)}'
    )
    extras = colony.explored - expected
    assert not extras, f'reveal leaked outside radius: {sorted(extras)}'


def test_reveal_clamps_to_world_bounds():
    # Agent at the corner — bottom and right rows of the 3x3 are out of
    # bounds and must not be added.
    sim, colony, agent = _sim_with_one_agent(agent_x=0, agent_y=0)
    sim._refresh_fog([agent])
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


def test_explored_persists_across_phase_boundaries():
    # Pin that the explored set sticks across every phase transition —
    # the prior dusk → night reset was removed because the demo prefers
    # cumulative discovery to a one-day-cycle reset. Walk the sim across
    # all four boundaries with pre-seeded fog and assert nothing wipes.
    sim, colony, _agent = _sim_with_one_agent(agent_x=4, agent_y=4)
    pre_seeded = {(0, 0), (9, 9), (5, 5)}
    for boundary_phase in ('dawn', 'day', 'dusk', 'night'):
        idx = cycle.PHASES.index(boundary_phase)
        sim.current_tick = idx * cycle.TICKS_PER_PHASE
        colony.explored.update(pre_seeded)
        sim.step()
        assert pre_seeded.issubset(colony.explored), (
            f'pre-seeded fog wiped on entry into {boundary_phase}: '
            f'missing {pre_seeded - colony.explored}'
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
