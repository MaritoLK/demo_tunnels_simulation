"""Runtime Agent and per-tick driver. Pure Python — no Flask, no DB imports."""
from . import actions, needs


class Agent:
    __slots__ = (
        'id', 'name', 'x', 'y', 'state',
        'hunger', 'energy', 'social', 'health',
        'age', 'alive',
    )

    def __init__(self, name, x, y, agent_id=None):
        self.id = agent_id
        self.name = name
        self.x = x
        self.y = y
        self.state = actions.STATE_IDLE
        self.hunger = needs.NEED_MAX
        self.energy = needs.NEED_MAX
        self.social = needs.NEED_MAX
        self.health = needs.NEED_MAX
        self.age = 0
        self.alive = True

    def __repr__(self):
        return f"Agent({self.name}@{self.x},{self.y},state={self.state})"


def decide_action(agent):
    if agent.health < needs.HEALTH_CRITICAL:
        return 'rest' if agent.energy < needs.ENERGY_CRITICAL else 'forage'
    if agent.hunger < needs.HUNGER_CRITICAL:
        return 'forage'
    if agent.energy < needs.ENERGY_CRITICAL:
        return 'rest'
    if agent.hunger < needs.HUNGER_MODERATE:
        return 'forage'
    if agent.social < needs.SOCIAL_LOW:
        return 'socialise'
    return 'explore'


def execute_action(action_name, agent, world, all_agents, *, rng):
    if action_name == 'forage':
        return actions.forage(agent, world, rng=rng)
    if action_name == 'rest':
        return actions.rest(agent)
    if action_name == 'socialise':
        return actions.socialise(agent, all_agents)
    if action_name == 'explore':
        return actions.explore(agent, world, rng=rng)
    return {'type': 'idled', 'description': f'{agent.name} did nothing'}


def tick_agent(agent, world, all_agents, *, rng):
    if not agent.alive:
        return []

    events = []

    # Pre-decay death check: an agent that entered the tick already at
    # zero health is semantically a corpse. Don't decay its needs first —
    # die immediately. The post-decay check below still catches the
    # common case where starvation drives health across the threshold
    # *this tick*.
    if agent.health <= 0:
        events.append(actions.die(agent))
        return events

    needs.decay_needs(agent)

    if agent.health <= 0:
        events.append(actions.die(agent))
        return events

    action_name = decide_action(agent)
    events.append(execute_action(action_name, agent, world, all_agents, rng=rng))

    agent.age += 1
    return events
