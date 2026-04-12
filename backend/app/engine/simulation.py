import random

from .agent import Agent, tick_agent
from .world import World


class Simulation:
    def __init__(self, world, agents=None, current_tick=0, seed=None):
        self.world = world
        self.agents = list(agents) if agents is not None else []
        self.current_tick = current_tick
        self.rng = random.Random(seed)

    @property
    def alive_agents(self):
        return [a for a in self.agents if a.alive]

    def add_agent(self, agent):
        self.agents.append(agent)

    def spawn_agent(self, name):
        walkable = [
            (t.x, t.y)
            for row in self.world.tiles
            for t in row
            if t.is_walkable
        ]
        if not walkable:
            raise RuntimeError('no walkable tiles to spawn on')
        x, y = self.rng.choice(walkable)
        agent = Agent(name, x, y)
        self.agents.append(agent)
        return agent

    def step(self):
        events = []
        snapshot = list(self.agents)
        for agent in snapshot:
            if not agent.alive:
                continue
            for event in tick_agent(agent, self.world, snapshot, rng=self.rng):
                event['tick'] = self.current_tick
                event['agent_id'] = agent.id
                events.append(event)
        self.current_tick += 1
        return events

    def run(self, ticks):
        batch = []
        for _ in range(ticks):
            batch.extend(self.step())
        return batch


def new_simulation(width, height, seed=None, agent_count=0, agent_name_prefix='Agent'):
    world = World(width, height)
    world.generate(seed=seed)
    sim = Simulation(world, seed=seed)
    for i in range(agent_count):
        sim.spawn_agent(f'{agent_name_prefix}-{i + 1}')
    return sim
