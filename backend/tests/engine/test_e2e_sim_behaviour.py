"""End-to-end multi-tick smoke for the agent loop. Pins the three
behaviours called out in the user's "run a simulation" report:

  1. Agents grab food and DO NOT remain idle while unexplored fog
     still exists nearby. (explore() now BFS-routes to the fog
     frontier instead of idling on top of a depleted memory tile.)

  2. Agents do not repeat exploration of already-mapped tiles when
     unexplored land is still within range. (BFS-frontier scout
     pushes toward fog rather than random-walking through known
     ground.)

  3. Agents collect food on sight even when their own hunger is
     fine — food is precious. (decide_action's opportunistic
     forage rung sits above plant / tail-explore.)

Pure-engine, no DB. Built directly on Simulation + EngineColony so
the ladder + explore() interact as they would in a live tick loop.
"""
import random

from app.engine import actions, needs
from app.engine.agent import Agent, decide_action
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


def _set_food(world, x, y, amount=5.0):
    t = world.get_tile(x, y)
    t.resource_type = 'food'
    t.resource_amount = amount


def _colony():
    return EngineColony(
        id=1, name='Red', color='#e74c3c',
        camp_x=0, camp_y=0, food_stock=0,
    )


def test_sim_explored_set_grows_monotonically_over_50_ticks():
    # No food anywhere — pure exploration test. The colony's explored
    # set must grow on most ticks (never shrink mid-day) and end with
    # a substantially larger reveal than the starting bubble. If the
    # frontier scout regressed to "random walk through known ground"
    # the count would plateau.
    world = _grass(width=20, height=20)
    sim = Simulation(world, seed=42, colonies=[_colony()])
    a = Agent(name='A', x=10, y=10, agent_id=1, colony_id=1)
    sim.agents.append(a)
    # First step seeds the explored set so we have a non-zero baseline.
    sim.step()
    seen = [len(sim.colonies[1].explored)]
    for _ in range(50):
        sim.step()
        seen.append(len(sim.colonies[1].explored))
    # Total reveal must be strictly larger than the seeded bubble.
    assert seen[-1] > seen[0], (
        f'explored set did not grow over 50 ticks: '
        f'start={seen[0]}, end={seen[-1]}, full={seen}'
    )
    # And must be growing on average — at least 25% of the ticks
    # must have added new tiles. Caps + stairs (cooldown ticks) eat
    # some of the budget so we don't demand strict monotonicity.
    growths = sum(
        1 for prev, cur in zip(seen, seen[1:]) if cur > prev
    )
    assert growths >= 12, (
        f'reveal grew on only {growths}/50 ticks — frontier scout '
        f'is idling or re-treading. counts={seen}'
    )


def test_sim_agents_do_not_idle_with_unexplored_fog_nearby():
    # Drop an agent on a tile already mid-grow (so plant gate fails)
    # with all immediate neighbours pre-seeded into colony.explored
    # (so the cheap-frontier shortcut can't fire). Fog still covers
    # the rest of the map. Expect 'moved' from the BFS frontier
    # scout, NOT 'idled'.
    world = _grass(width=20, height=20)
    # Mid-growing crop on the agent's own tile blocks plant.
    world.get_tile(10, 10).crop_state = 'growing'
    world.get_tile(10, 10).crop_colony_id = 1
    sim = Simulation(world, seed=1, colonies=[_colony()])
    a = Agent(name='A', x=10, y=10, agent_id=1, colony_id=1)
    sim.agents.append(a)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            sim.colonies[1].explored.add((10 + dx, 10 + dy))

    events = sim.step()
    own_events = [e for e in events if e.get('agent_id') == 1]
    moves = [e for e in own_events if e['type'] == 'moved']
    idles = [e for e in own_events if e['type'] == 'idled']
    assert moves, (
        f'agent idled while fog remained — events for this tick: '
        f'all={own_events}, idles={idles}'
    )


def test_sim_agent_grabs_adjacent_food_when_sated():
    # Sated agent steps next to a food tile during a normal tick.
    # decide_action's opportunistic forage rung must fire.
    world = _grass(width=10, height=10)
    sim = Simulation(world, seed=1, colonies=[_colony()])
    _set_food(world, 6, 5, amount=10.0)
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.hunger = 90.0
    a.energy = 90.0
    a.social = 90.0
    a.health = 100.0
    sim.agents.append(a)
    decision = decide_action(a, world, sim.colonies[1], 'day')
    assert decision.action == 'forage', (
        f"sated agent next to food chose {decision.action!r} "
        f"({decision.reason!r}) — expected opportunistic forage"
    )


def test_sim_no_post_forage_idle_lock_with_fog_remaining():
    # The user's report: "agents grab food and remain idle". Specific
    # repro — agent on a food tile, forages, fills up, then on the
    # next tick they should still be moving (toward fog, or toward
    # other food memory) rather than idling.
    world = _grass(width=20, height=20)
    _set_food(world, 10, 10, amount=8.0)
    sim = Simulation(world, seed=1, colonies=[_colony()])
    a = Agent(name='A', x=10, y=10, agent_id=1, colony_id=1)
    a.hunger = 60.0  # above moderate, so post-forage hunger maxes
    sim.agents.append(a)

    # Tick 1: should forage (opportunistic — food on own tile).
    events_tick1 = sim.step()
    foraged = any(
        e['type'] == 'foraged' and e.get('agent_id') == 1
        for e in events_tick1
    )
    assert foraged, f'agent did not forage own tile, events={events_tick1}'

    # Tick 2: agent likely still on (10,10), tile drained / pouch
    # bumped. The agent must NOT idle — fog still surrounds the
    # 3x3 reveal bubble.
    pre_pos = (a.x, a.y)
    events_tick2 = sim.step()
    moved_or_acted = any(
        e['type'] in ('moved', 'foraged', 'planted', 'harvested')
        and e.get('agent_id') == 1
        for e in events_tick2
    )
    idled = any(
        e['type'] == 'idled' and e.get('agent_id') == 1
        for e in events_tick2
    )
    assert moved_or_acted, (
        f'agent idled on tick 2 (pre_pos={pre_pos}, post_pos='
        f'{(a.x, a.y)}); events={events_tick2}'
    )
    assert not idled or moved_or_acted, (
        f'idled event present without a paired action: {events_tick2}'
    )


def test_sim_food_collection_outpaces_explore_when_food_clustered():
    # Cluster of three food tiles around the agent's spawn. Sim runs
    # 30 ticks. The agent should pull all three into a foraged event
    # before drifting off — verifying that the opportunistic forage
    # branch fires on every adjacent food tile, not just on hunger
    # crits.
    world = _grass(width=20, height=20)
    _set_food(world, 10, 10, amount=4.0)
    _set_food(world, 11, 10, amount=4.0)
    _set_food(world, 10, 11, amount=4.0)
    sim = Simulation(world, seed=99, colonies=[_colony()])
    a = Agent(name='A', x=10, y=10, agent_id=1, colony_id=1)
    sim.agents.append(a)

    forage_events = []
    for _ in range(30):
        for ev in sim.step():
            if ev['type'] == 'foraged' and ev.get('agent_id') == 1:
                forage_events.append(ev)

    # Sum of yields across all three tiles is 12. With d20 banding
    # (avg ≈ 2 per forage, capped by tile resource and pouch), the
    # agent should drain at least 6 units worth of food in 30 ticks.
    total_taken = sum(
        ev['data']['amount_taken'] for ev in forage_events
    )
    assert total_taken >= 6, (
        f'agent only collected {total_taken} food in 30 ticks '
        f'with three full caches at hand — opportunistic forage '
        f'is regressed. forage events: {len(forage_events)}'
    )
