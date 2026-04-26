"""Simulation container and tick driver. Pure Python — no Flask, no DB imports."""
import hashlib
import random

from .agent import Agent, tick_agent
from .colony import EngineColony
from .world import World
from . import config, cycle, skill


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
    def __init__(self, world, agents=None, current_tick=0, seed=None, colonies=None):
        self.world = world
        self.agents = list(agents) if agents is not None else []
        self.current_tick = current_tick
        self.seed = seed
        self.rng_spawn = random.Random(_sub_seed(seed, 'spawn'))
        self.rng_tick = random.Random(_sub_seed(seed, 'tick'))
        if colonies:
            self.colonies = {c.id: c for c in colonies}
        else:
            # Synthesize a default colony for callers that don't supply one
            # (the agent_count= convenience overload in new_simulation, direct
            # Simulation() in unit tests). Keys on None so agents constructed
            # without an explicit colony_id (Agent default == None) match the
            # colony lookup in tick_agent. Lets the engine run a single,
            # colony-aware tick path instead of branching on legacy shape.
            default = EngineColony(id=None, name='_default', color='#000',
                                   camp_x=0, camp_y=0,
                                   food_stock=config.INITIAL_FOOD_STOCK,
                                   growing_count=0,
                                   sprite_palette='Blue')
            self.colonies = {None: default}

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
        phase = cycle.phase_for(self.current_tick)

        # Fog reset: at the dusk → night phase boundary, every colony's
        # explored set drops back to empty. Without this fog accumulates
        # forever and exploration is a one-time tax. Pinning the reset to
        # nightfall gives each day a stake — the colony has to find its
        # food before sunset or wake up tomorrow with the map dark again.
        if self.current_tick > 0:
            prev_phase = cycle.phase_for(self.current_tick - 1)
            if prev_phase != 'night' and phase == 'night':
                for colony in self.colonies.values():
                    colony.explored.clear()

        self.recompute_growing_counts()
        snapshot = list(self.agents)
        for agent in snapshot:
            if not agent.alive:
                continue
            for event in tick_agent(
                agent, self.world, snapshot, self.colonies,
                phase=phase, rng=self.rng_tick,
            ):
                event['tick'] = self.current_tick
                event['agent_id'] = agent.id
                events.append(event)

        # Fog reveal: each non-rogue alive agent paints its colony's
        # REVEAL_RADIUS square onto colony.explored. Run after the agent
        # tick loop so the reveal reflects where the agent actually
        # ended up this tick. Rogue agents skip — no colony tie, no fog
        # contribution, mirrors the rogue exclusion in the camp branches
        # of the decision ladder.
        self._refresh_fog(snapshot)

        for event in self.world.tick(phase):
            event['tick'] = self.current_tick
            events.append(event)
        self.current_tick += 1
        return events

    def _refresh_fog(self, snapshot):
        width = self.world.width
        height = self.world.height
        for agent in snapshot:
            if not agent.alive or agent.rogue:
                continue
            if agent.colony_id is None:
                continue
            colony = self.colonies.get(agent.colony_id)
            if colony is None:
                continue
            # Per-agent reveal radius scales with their walk-skill
            # tier — veteran scouts uncover a wider area than fresh
            # spawns. Apprentice = 3x3, journeyman = 5x5, veteran =
            # 7x7 (see engine.skill).
            radius = skill.reveal_radius_for(agent.tiles_walked)
            ax, ay = agent.x, agent.y
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    tx = ax + dx
                    ty = ay + dy
                    if 0 <= tx < width and 0 <= ty < height:
                        colony.explored.add((tx, ty))

    def recompute_growing_counts(self):
        """Re-derive `colony.growing_count` from tile state.
        Called at the start of each `step`. O(tiles) per tick."""
        counts = {cid: 0 for cid in self.colonies}
        for row in self.world.tiles:
            for tile in row:
                if tile.crop_state == 'growing' and tile.crop_colony_id in counts:
                    counts[tile.crop_colony_id] += 1
        for cid, colony in self.colonies.items():
            colony.growing_count = counts[cid]

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


def new_simulation(width, height, seed=None, agent_count=0, agent_name_prefix='Agent',
                   colonies=None, agents_per_colony=None):
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
    # Colony kwargs travel as a pair: either both set (colony-aware spawn)
    # or both None (random spawn under the synthesized default colony).
    # Half-set routes silently to the wrong branch and blows up 3 frames
    # deep in tick_agent's missing-colony_id invariant — fail loud at the
    # seam instead.
    if (colonies is None) != (agents_per_colony is None):
        raise ValueError(
            'colonies and agents_per_colony must be passed together; '
            f'got colonies={colonies!r}, agents_per_colony={agents_per_colony!r}'
        )
    world = World(width, height)
    world.generate(seed=seed)
    sim = Simulation(world, seed=seed, colonies=colonies)
    if colonies is not None and agents_per_colony is not None:
        for colony in colonies:
            for i in range(agents_per_colony):
                name = f'{colony.name}-{i + 1}'
                a = Agent(name, colony.camp_x, colony.camp_y, colony_id=colony.id)
                sim.agents.append(a)
    else:
        for i in range(agent_count):
            sim.spawn_agent(f'{agent_name_prefix}-{i + 1}')
    # Loner promotion: sims large enough to have "social depth" (>4 agents)
    # get exactly two loners. Selection draws from rng_spawn so it's
    # reproducible under the sim seed contract. Small sims get none —
    # skipping the branch keeps legacy 2-4 agent tests behaving identically.
    _LONER_MIN_POPULATION = 4
    _LONER_COUNT = 2
    if len(sim.agents) > _LONER_MIN_POPULATION:
        for loner in sim.rng_spawn.sample(sim.agents, _LONER_COUNT):
            loner.loner = True
    return sim
