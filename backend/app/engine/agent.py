from . import actions, needs


class Agent:
    __slots__ = (
        'id', 'name', 'x', 'y', 'state',
        'hunger', 'energy', 'social', 'health',
        'age', 'alive',
    )

    def __init__(self, name, x, y, id=None):
        self.id = id
        self.name = name
        self.x = x
        self.y = y
        self.state = 'idle'
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


def execute_action(action_name, agent, world, all_agents, rng=None):
    if action_name == 'forage':
        return actions.forage(agent, world)
    if action_name == 'rest':
        return actions.rest(agent)
    if action_name == 'socialise':
        return actions.socialise(agent, all_agents)
    if action_name == 'explore':
        return actions.explore(agent, world, rng=rng)
    return {'type': 'idled', 'description': f'{agent.name} did nothing'}


def tick_agent(agent, world, all_agents, rng=None):
    if not agent.alive:
        return []

    events = []
    needs.decay_needs(agent)

    if agent.energy <= 0:
        agent.state = 'resting'

    if agent.health <= 0:
        events.append(actions.die(agent))
        return events

    action_name = decide_action(agent)
    events.append(execute_action(action_name, agent, world, all_agents, rng=rng))

    agent.age += 1
    return events
