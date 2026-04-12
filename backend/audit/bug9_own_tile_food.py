"""
Audit Correctness #1 — adjacent_food_tile checks only the 4 cardinal
neighbours, never the agent's own tile. An agent standing on food can
never eat it.

Worse: forage() falls back to find_nearest_tile which *does* return the
agent's own tile. step_toward with dx=dy=0 has no candidates → returns
False → falls through to explore. On a 1x1 world explore finds no
walkable neighbours → agent idles every tick and starves standing on food.

Test: 1x1 grass world with a food tile. Spawn agent on it, seed hunger
just below HUNGER_MODERATE so decide_action picks 'forage' every tick.
Run 100 ticks, count 'foraged' events, observe final hunger.
  Pre-fix: 0 forages. Hunger decays monotonically.
  Post-fix: multiple forages. Hunger stays near full.
"""
import random

from app.engine import actions, needs
from app.engine.agent import Agent, tick_agent
from app.engine.world import World, Tile


TICKS = 100


def food_world():
    w = World(1, 1)
    w.tiles = [[Tile(0, 0, 'grass', 'food', 50.0)]]
    return w


def legacy_adjacent_food_tile(agent, world):
    """Pre-fix: cardinal neighbours only, own tile ignored."""
    for dx, dy in actions.DIRECTIONS:
        nx, ny = agent.x + dx, agent.y + dy
        if not world.in_bounds(nx, ny):
            continue
        tile = world.get_tile(nx, ny)
        if tile.resource_type == 'food' and tile.resource_amount > 0:
            return tile
    return None


def run_trial(use_legacy):
    original = actions.adjacent_food_tile
    if use_legacy:
        actions.adjacent_food_tile = legacy_adjacent_food_tile
    try:
        world = food_world()
        agent = Agent('Alice', 0, 0)
        agent.hunger = needs.HUNGER_MODERATE - 1
        rng = random.Random(0)
        forage_count = 0
        for _ in range(TICKS):
            events = tick_agent(agent, world, [agent], rng=rng)
            forage_count += sum(1 for e in events if e['type'] == 'foraged')
        return forage_count, agent.hunger, world.tiles[0][0].resource_amount
    finally:
        actions.adjacent_food_tile = original


def report(label, forages, hunger, tile_food):
    print(f'{label}')
    print(f'  forage events    : {forages}')
    print(f'  final hunger     : {hunger:.1f}')
    print(f'  food left on tile: {tile_food:.1f}')
    print()


def main():
    print(f'1x1 world, food tile at (0,0), agent spawned on it, {TICKS} ticks.\n')
    report('Pre-fix  (adjacent only)', *run_trial(use_legacy=True))
    report('Post-fix (own + adjacent)', *run_trial(use_legacy=False))


if __name__ == '__main__':
    main()
