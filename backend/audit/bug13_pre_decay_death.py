"""
Audit Correctness #4 (r3) — tick_agent runs decay_needs before checking
health <= 0. An agent that enters a tick already at health=0 (loaded from
DB mid-catastrophe, constructed directly in a test, or engineered by some
future combat/disease path) has hunger/energy/social decremented once
more before the death event fires.

The current post-decay death check is correct for *starvation-crossed-the-line
this tick* — decay is what drives health from positive to zero. But it
swallows the *already at zero* case: a zero-health agent is semantically
a corpse, and corpses don't get hungrier.

Test: construct an agent with health=0, alive=True, hunger=50. One tick.
  Pre-fix: hunger, energy, social all decremented; then die() fires.
  Post-fix: die() fires first (pre-decay check); needs untouched.

The fix is a two-tier death check — pre-decay admits already-zero corpses;
post-decay preserves starvation-death detection.
"""
import random

from app.engine import agent as agent_module
from app.engine.agent import Agent, tick_agent
from app.engine.world import World, Tile


def plain_world():
    w = World(3, 3)
    w.tiles = [[Tile(x, y, 'grass') for x in range(3)] for y in range(3)]
    return w


def legacy_tick_agent(agent, world, all_agents, *, rng):
    """Pre-fix: decay first, then check health. Corpse gets one last hunger pang."""
    if not agent.alive:
        return []
    events = []
    agent_module.needs.decay_needs(agent)
    if agent.health <= 0:
        events.append(agent_module.actions.die(agent))
        return events
    action_name = agent_module.decide_action(agent)
    events.append(agent_module.execute_action(action_name, agent, world, all_agents, rng=rng))
    agent.age += 1
    return events


def run_trial(tick_fn):
    world = plain_world()
    agent = Agent('Alice', 1, 1)
    agent.health = 0.0  # already dead by health; still flagged alive
    agent.hunger = 50.0
    agent.energy = 50.0
    agent.social = 50.0
    events = tick_fn(agent, world, [agent], rng=random.Random(0))
    return events, agent


def report(label, events, agent):
    event_types = [e['type'] for e in events]
    print(f'{label}')
    print(f"  events         : {event_types}")
    print(f'  final hunger   : {agent.hunger:.1f}')
    print(f'  final energy   : {agent.energy:.1f}')
    print(f'  final social   : {agent.social:.1f}')
    print(f'  alive          : {agent.alive}')
    print()


def main():
    print('Agent starts tick: health=0, hunger=50, energy=50, social=50, alive=True.\n')
    report('Pre-fix  (decay then check)', *run_trial(legacy_tick_agent))
    report('Post-fix (pre-decay check)', *run_trial(tick_agent))


if __name__ == '__main__':
    main()
