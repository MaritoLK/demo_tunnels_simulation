"""Simulation container and tick driver. Pure Python — no Flask, no DB imports."""
import hashlib
import random

from .agent import Agent, tick_agent
from .world import World


def _sub_seed(master, key):
    """Derive an independent seed for a named concern from a master seed.

    Using a single `random.Random(seed)` across spawn-position picking and
    per-tick decisions couples the two: adding a spawn shifts every
    subsequent tick's randomness. Deriving `rng_spawn` and `rng_tick` from
    independent hashes of the master seed keeps each stream reproducible
    on its own terms.
    """
    if master is None:
        return None
    payload = f'{master}:{key}'.encode()
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, 'big')


def _rng_state_to_json(rng):
    """Convert `random.Random.getstate()` to a JSON-safe shape.

    `getstate()` returns `(version, tuple_of_ints, gauss_next)`. JSONB
    can't hold tuples, so we convert the inner tuple to a list and wrap
    the whole thing as a list. Round-trip restored via `_rng_state_from_json`.
    """
    version, internal_state, gauss_next = rng.getstate()
    return [version, list(internal_state), gauss_next]


def _rng_state_from_json(snapshot):
    """Inverse of `_rng_state_to_json`. Returns the tuple `setstate()` expects."""
    version, internal_state, gauss_next = snapshot
    return (version, tuple(internal_state), gauss_next)


class Simulation:
    def __init__(self, world, agents=None, current_tick=0, seed=None):
        self.world = world
        self.agents = list(agents) if agents is not None else []
        self.current_tick = current_tick
        self.seed = seed
        self.rng_spawn = random.Random(_sub_seed(seed, 'spawn'))
        self.rng_tick = random.Random(_sub_seed(seed, 'tick'))

    def snapshot_rng_state(self):
        """JSON-safe snapshot of both sub-stream RNGs for persistence."""
        return {
            'spawn': _rng_state_to_json(self.rng_spawn),
            'tick': _rng_state_to_json(self.rng_tick),
        }

    def restore_rng_state(self, snapshot):
        """Reinstate sub-stream RNG trajectories from a prior snapshot."""
        self.rng_spawn.setstate(_rng_state_from_json(snapshot['spawn']))
        self.rng_tick.setstate(_rng_state_from_json(snapshot['tick']))

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
        # Prefer an unoccupied walkable tile. Falling back to any walkable
        # only when the world is fully packed keeps the engine correct on
        # tiny maps (and in that edge case agents can still socialise out
        # of the stack now that adjacent_agent includes co-location).
        occupied = {(a.x, a.y) for a in self.agents if a.alive}
        free = [pos for pos in walkable if pos not in occupied]
        choices = free if free else walkable
        x, y = self.rng_spawn.choice(choices)
        agent = Agent(name, x, y)
        self.agents.append(agent)
        return agent

    def step(self):
        events = []
        snapshot = list(self.agents)
        for agent in snapshot:
            if not agent.alive:
                continue
            for event in tick_agent(agent, self.world, snapshot, rng=self.rng_tick):
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


# Engine-layer invariants. Duplicated at the route layer for input-shape
# gating; kept here as the last trust boundary — any caller (tests, future
# CLI, direct service import) is rejected loudly on nonsense sizes rather
# than OOM-ing the process or blowing out a single DB transaction.
MAX_WORLD_CELLS = 10_000
MAX_AGENTS = 1000


def new_simulation(width, height, seed=None, agent_count=0, agent_name_prefix='Agent'):
    if not (isinstance(width, int) and isinstance(height, int)):
        raise ValueError('width and height must be ints')
    if width < 1 or height < 1:
        raise ValueError(f'width and height must be >= 1, got {width}x{height}')
    if width * height > MAX_WORLD_CELLS:
        raise ValueError(
            f'world {width}x{height}={width * height} exceeds MAX_WORLD_CELLS={MAX_WORLD_CELLS}'
        )
    if not isinstance(agent_count, int) or agent_count < 0:
        raise ValueError(f'agent_count must be non-negative int, got {agent_count!r}')
    if agent_count > min(width * height, MAX_AGENTS):
        raise ValueError(
            f'agent_count={agent_count} exceeds min(world_cells={width * height}, MAX_AGENTS={MAX_AGENTS})'
        )
    world = World(width, height)
    world.generate(seed=seed)
    sim = Simulation(world, seed=seed)
    for i in range(agent_count):
        sim.spawn_agent(f'{agent_name_prefix}-{i + 1}')
    return sim
