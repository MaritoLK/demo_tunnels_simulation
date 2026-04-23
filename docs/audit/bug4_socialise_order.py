"""
Audit Bug #4 — socialise mutates BOTH agents; iteration order can affect outcome.

The socialise action (actions.py:88-98) bumps agent.social AND other.social by +20.
In Simulation.step, agents are ticked in list order. The second agent's tick sees
the first agent's mutation already applied. For most starting conditions this is
self-correcting (decay hits both), but when the +20 bump collides with the NEED_MAX
cap, the clamping happens at different times for each agent, producing order-
dependent end-state.

Test: two adjacent agents, A starts at social=95 (near the cap), B starts at 20
(below SOCIAL_LOW so will initiate socialise). Tick once under order [A,B] and
once under [B,A]. Compare A's final social value.
"""
import random

from app.engine.world import Tile, World
from app.engine.agent import Agent, tick_agent


def build_world():
    w = World(2, 1)
    w.tiles = [[Tile(0, 0, 'grass'), Tile(1, 0, 'grass')]]
    return w


def trial(order):
    w = build_world()
    a = Agent('A', 0, 0)
    a.social = 95.0
    b = Agent('B', 1, 0)
    b.social = 20.0
    agents = [a, b] if order == 'AB' else [b, a]
    rng = random.Random(42)
    for agent in agents:
        tick_agent(agent, w, [a, b], rng=rng)
    return (a.social, b.social)


def main():
    ab = trial('AB')
    ba = trial('BA')
    print(f'order [A, B]: A.social={ab[0]:.2f}, B.social={ab[1]:.2f}')
    print(f'order [B, A]: A.social={ba[0]:.2f}, B.social={ba[1]:.2f}')
    if ab != ba:
        diff = max(abs(ab[0] - ba[0]), abs(ab[1] - ba[1]))
        print(f'\nOrder-dependent: yes. Max delta = {diff:.2f}')
    else:
        print('\nOrder-dependent: no')


if __name__ == '__main__':
    main()
