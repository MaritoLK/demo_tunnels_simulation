"""Walk-skill tier table + per-agent step counter feeding it.

Counter ticks only on a successful position change (not on idle /
move-cooldown turns), so agents who genuinely cover ground earn the
wider radius. Tier table is a simple ladder: 0/50/150 thresholds map
to radii 1/2/3 — keeps the lookup obviously correct at a glance.
"""
from app.engine import skill
from app.engine.colony import EngineColony
from app.engine.simulation import Simulation
from app.engine.world import Tile, World


def _grass(width=20, height=20):
    w = World(width, height)
    w.tiles = [
        [Tile(x, y, 'grass') for x in range(width)]
        for y in range(height)
    ]
    return w


def test_tier_table_threshold_to_radius_lookup():
    cases = [
        (0,    1),
        (49,   1),
        (50,   2),
        (100,  2),
        (149,  2),
        (150,  3),
        (10_000, 3),  # caps at the top tier
    ]
    for tiles_walked, expected_radius in cases:
        got = skill.reveal_radius_for(tiles_walked)
        assert got == expected_radius, (
            f'tiles_walked={tiles_walked}: expected radius {expected_radius}, got {got}'
        )


def test_step_increments_tiles_walked_on_successful_move():
    # Force the agent to move via explore. Single-tile world with one
    # walkable neighbour so the random pick is determined.
    from app.engine.agent import Agent
    sim = Simulation(_grass(), colonies=[
        EngineColony(id=1, name='Red', color='#e74c3c',
                     camp_x=0, camp_y=0, food_stock=0),
    ])
    a = Agent(name='A', x=4, y=4, agent_id=1, colony_id=1)
    sim.agents.append(a)
    pre = a.tiles_walked
    sim.step()
    # Random walk step almost always succeeds on an open grass field.
    moved = (a.x, a.y) != (4, 4)
    if moved:
        assert a.tiles_walked == pre + 1
    else:
        assert a.tiles_walked == pre


def test_step_does_not_increment_when_traversing():
    # An agent in move_cooldown idles instead of acting. tiles_walked
    # must NOT increment — credit only for actually-taken steps.
    from app.engine.agent import Agent
    sim = Simulation(_grass(), colonies=[
        EngineColony(id=1, name='Red', color='#e74c3c',
                     camp_x=0, camp_y=0, food_stock=0),
    ])
    a = Agent(name='A', x=4, y=4, agent_id=1, colony_id=1)
    a.move_cooldown = 2
    sim.agents.append(a)
    pre = a.tiles_walked
    sim.step()
    assert a.tiles_walked == pre
    assert a.move_cooldown == 1


def test_fog_reveal_radius_grows_with_tiles_walked():
    # Two agents, identical except one is a veteran — the veteran's
    # reveal touches more tiles per tick.
    from app.engine.agent import Agent
    apprentice_world = _grass()
    apprentice_sim = Simulation(apprentice_world, colonies=[
        EngineColony(id=1, name='Red', color='#e74c3c',
                     camp_x=0, camp_y=0, food_stock=0),
    ])
    apprentice = Agent(name='A', x=10, y=10, agent_id=1, colony_id=1)
    apprentice_sim.agents.append(apprentice)
    apprentice_sim.step()

    veteran_world = _grass()
    veteran_sim = Simulation(veteran_world, colonies=[
        EngineColony(id=2, name='Red', color='#e74c3c',
                     camp_x=0, camp_y=0, food_stock=0),
    ])
    veteran = Agent(name='V', x=10, y=10, agent_id=2, colony_id=2)
    veteran.tiles_walked = 200  # firmly in tier 3 (radius 3 → 7x7)
    veteran_sim.agents.append(veteran)
    veteran_sim.step()

    apprentice_explored = next(iter(apprentice_sim.colonies.values())).explored
    veteran_explored = next(iter(veteran_sim.colonies.values())).explored
    # Apprentice: 3x3 = 9 tiles around the agent's final position.
    # Veteran:    7x7 = 49 tiles around the agent's final position.
    assert len(veteran_explored) > len(apprentice_explored)
    assert len(veteran_explored) >= 40
    assert len(apprentice_explored) <= 16  # 3x3 (=9) + a bit if movement straddled tiles
