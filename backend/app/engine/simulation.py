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
        self._ensure_walkable_camp_tiles()

    def _ensure_walkable_camp_tiles(self):
        """Carve a walkable 3×3 grass bubble around each colony's camp.

        World generation picks terrain by biome distance and the
        default-corner camp positions (see services._default_camp_positions)
        can roll any terrain — including water. Two failure modes traced
        in the 2026-04-26 1500-tick diagnostic:

          1. Camp tile itself is water — agents spawn on a non-walkable
             tile, can't act. Hunger drains; they starve at ~tick 270.
          2. Camp tile is a 1-tile grass island in a water lake — agents
             can plant but every cardinal neighbour is water, so the
             BFS frontier scout returns no targets. Same outcome.

        Clearing the 3×3 around the camp guarantees the agents have at
        least 8 walkable neighbours to push off into, breaking the
        island. Resources on the cleared tiles are stripped — camps
        are colony infrastructure, not landscape, and a phantom food
        cache on a "water that became grass" tile would forage as if
        it were a real cluster. One-shot at __init__: camps don't move.
        """
        for colony in self.colonies.values():
            cx, cy = colony.camp_x, colony.camp_y
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    tx, ty = cx + dx, cy + dy
                    if not self.world.in_bounds(tx, ty):
                        continue
                    tile = self.world.get_tile(tx, ty)
                    if tile.is_walkable and tile.resource_type is None:
                        # Already a clean walkable tile — leave it
                        # alone so the camp neighbourhood inherits the
                        # surrounding biome flavor when nothing's broken.
                        continue
                    tile.terrain = 'grass'
                    tile.resource_type = None
                    tile.resource_amount = 0.0
                    tile.crop_state = 'none'
                    tile.crop_growth_ticks = 0
                    tile.crop_colony_id = None

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

        # Dawn-meal reproduction. Runs AFTER the agent tick loop so the
        # newborn enters the world at age=0 and skips the current tick's
        # decision pass — they "rest" their first tick, joining the
        # snapshot only on the next step. Avoids the surprising
        # behaviour of a freshly-named child immediately deciding to
        # eat at camp.
        if phase == 'dawn':
            events.extend(self._maybe_reproduce())

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

    def _maybe_reproduce(self):
        """Roll dawn-meal reproduction for each colony, return events.

        See config.REPRODUCTION_* for tuning. The per-colony gate is:
          * food_stock >= REPRODUCTION_FOOD_THRESHOLD
          * REPRODUCTION_COOLDOWN_TICKS elapsed since last birth
          * population < MAX_AGENTS_PER_COLONY
          * at least one alive non-rogue colony agent on the camp tile

        Why these gates: cooldown caps birth rate (otherwise a steady
        food surplus would carpet the camp in ticks). Pop cap stops
        unbounded growth. The midwife requirement keeps the trigger
        tied to an actual home presence — pre-design the user
        considered the both-on-camp socialise gate but the diagnostic
        showed that fired only 4 times in 1500 ticks; the single
        midwife is much more reliable.
        """
        born_events = []
        tick = self.current_tick
        for colony in self.colonies.values():
            if colony.id is None:
                # Default synthesized colony (legacy test path) doesn't
                # reproduce — keeps unit tests with no explicit colony
                # untouched.
                continue
            if colony.food_stock < config.REPRODUCTION_FOOD_THRESHOLD:
                continue
            if (colony.last_reproduction_tick is not None
                    and tick - colony.last_reproduction_tick
                    < config.REPRODUCTION_COOLDOWN_TICKS):
                continue
            pop = sum(1 for a in self.agents
                      if a.alive and a.colony_id == colony.id)
            if pop >= config.MAX_AGENTS_PER_COLONY:
                continue
            # Midwife: at least one alive non-rogue colony member,
            # location-agnostic. Pre-tuning we required them on (or
            # adjacent to) the camp tile but the diagnostic showed
            # agents are scattered in the field at most dawn ticks —
            # only 3 births fired across 20 demo days. The colony as a
            # whole is the social unit; any living non-rogue member
            # carries the colony forward. The newborn still spawns AT
            # the camp tile, so the visual is a 'baby appears at home'
            # cue regardless of where the rest of the colony is.
            midwife = next(
                (a for a in self.agents
                 if a.alive and not a.rogue
                 and a.colony_id == colony.id),
                None,
            )
            if midwife is None:
                continue
            # Spawn at camp. ID stays None — the persistence layer
            # assigns when the agent first hits the DB on the next
            # commit. Newborn starts well-fed/rested so they don't
            # immediately starve. Name uses the colony's monotonic
            # counter so names never collide across the colony's
            # lifetime, even after deaths free up alive-slot indices.
            colony.agent_name_counter += 1
            child = Agent(
                name=f'{colony.name}-{colony.agent_name_counter}',
                x=colony.camp_x,
                y=colony.camp_y,
                colony_id=colony.id,
            )
            self.agents.append(child)
            colony.food_stock -= config.REPRODUCTION_FOOD_COST
            colony.last_reproduction_tick = tick
            born_events.append({
                'type': 'birthed',
                'description': f'{child.name} was born at camp',
                'tick': tick,
                'agent_id': None,
                'data': {
                    'colony_id': colony.id,
                    'midwife_name': midwife.name,
                    'name': child.name,
                    'tile_x': colony.camp_x,
                    'tile_y': colony.camp_y,
                },
            })
        return born_events

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
            # Seed the colony's name counter past the founders so the
            # first newborn picks up Red-5 (or whatever) instead of
            # colliding with Red-1..Red-4.
            colony.agent_name_counter = agents_per_colony
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
