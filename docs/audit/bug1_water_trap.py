"""
Audit Bug #1 — step_toward water trap.

Setup: 3x2 grid. Agent at (0,0). Food at (2,0). Water at (1,0).
The greedy step_toward tries to go RIGHT (primary axis, dx=2 > |dy|=0), hits water,
has no secondary fallback (dy=0), returns False. forage reports "blocked" every tick
without moving. Agent cannot reach food even though the detour (0,0)→(0,1)→(1,1)→
(2,1)→food is trivial.

We pin hunger to 49 so the decision tree enters forage immediately (no pre-explore).

Expected (bug present):  agent stuck at (0,0), dies of starvation.
Expected (bug fixed):    agent routes around water via explore fallback, reaches food.
"""
import random

from app.engine.world import Tile, World
from app.engine.agent import Agent, tick_agent


def build_trap_world():
    w = World(3, 2)
    w.tiles = [
        # row y=0: G W F
        [
            Tile(0, 0, 'grass'),
            Tile(1, 0, 'water'),
            Tile(2, 0, 'grass', resource_type='food', resource_amount=20.0),
        ],
        # row y=1: G G G
        [
            Tile(0, 1, 'grass'),
            Tile(1, 1, 'grass'),
            Tile(2, 1, 'grass'),
        ],
    ]
    return w


def main():
    world = build_trap_world()
    agent = Agent('Trapped', 0, 0)
    agent.hunger = 49.0
    rng = random.Random(42)

    print(f'initial: pos=({agent.x},{agent.y}) hunger={agent.hunger}')

    positions = [(agent.x, agent.y)]
    event_counts = {}
    reached_food = False
    for tick in range(200):
        events = tick_agent(agent, world, [agent], rng=rng)
        for e in events:
            event_counts[e['type']] = event_counts.get(e['type'], 0) + 1
            if e['type'] == 'foraged':
                reached_food = True
        positions.append((agent.x, agent.y))
        if not agent.alive:
            print(f'\nDIED at tick {tick}')
            break
        if reached_food:
            print(f'\nREACHED FOOD at tick {tick}')
            break

    unique_positions = sorted(set(positions))
    print(f'final: pos=({agent.x},{agent.y}) alive={agent.alive} '
          f'hunger={agent.hunger:.1f} health={agent.health:.1f}')
    print(f'unique positions visited: {unique_positions}')
    print(f'event counts: {event_counts}')


if __name__ == '__main__':
    main()
