"""Action functions. Each returns an event dict and mutates the agent / world.

Pure Python — no Flask, no DB imports. Safe to unit-test without fixtures.

Any action that consumes randomness takes `rng` as a keyword-only required
argument — no silent fallback to the `random` module. The engine's
reproducibility contract (sub-seeded rng_spawn / rng_tick, see §9.11) is
only useful if every caller threads rng through; enforcing it at the
signature makes the contract impossible to bypass by accident.
"""
from collections import deque

from . import config, needs


DIRECTIONS = [(0, 1), (0, -1), (1, 0), (-1, 0)]

# Ticks a successful step consumes, keyed by *destination* terrain.
# Cost 1 = normal (no added wait); cost N sets agent.move_cooldown = N-1 so
# the agent is blocked from acting for N-1 subsequent ticks.
# Water is absent — is_walkable blocks entry entirely.
TERRAIN_MOVE_COST = {
    'grass': 1,
    'forest': 2,
    'sand': 2,
    'stone': 3,
}

STATE_IDLE = 'idle'
STATE_RESTING = 'resting'
STATE_FORAGING = 'foraging'
STATE_SOCIALISING = 'socialising'
STATE_EXPLORING = 'exploring'
STATE_TRAVERSING = 'traversing'
STATE_PLANTING = 'planting'
STATE_HARVESTING = 'harvesting'
STATE_DEPOSITING = 'depositing'
STATE_EATING = 'eating'
STATE_DEAD = 'dead'


# BFS search horizon. Tiles further than this (Manhattan-hop on walkable
# tiles) won't be pathed to — the caller falls through to random walk.
# 40 is ~2/3 the diagonal of the demo's 60x60 map: comfortably enough to
# reach any visible target, and bounds per-tick CPU at ~1600 node visits
# per agent in the worst case.
PATH_SEARCH_HORIZON = 40


def _first_step_bfs(agent, target_x, target_y, world):
    """Return the (dx, dy) for the first step of a shortest walkable path
    from the agent to (target_x, target_y), or None if unreachable within
    PATH_SEARCH_HORIZON.

    The target tile itself is accepted even if not walkable, so callers
    can route toward e.g. a camp marker without coupling this function
    to camp-tile semantics. Mid-path tiles must be walkable.
    """
    sx, sy = agent.x, agent.y
    if (sx, sy) == (target_x, target_y):
        return None

    # first_dir[(x,y)] = the step taken FROM start to begin reaching
    # (x,y). Reconstructing full paths isn't needed — we only ever act
    # on the next step, so tracking the first direction per wavefront
    # node is enough and avoids a second parent-chain walk.
    first_dir = {(sx, sy): None}
    queue = deque([(sx, sy, 0)])
    while queue:
        x, y, depth = queue.popleft()
        if depth >= PATH_SEARCH_HORIZON:
            continue
        for ddx, ddy in DIRECTIONS:
            nx, ny = x + ddx, y + ddy
            if (nx, ny) in first_dir:
                continue
            if not world.in_bounds(nx, ny):
                continue
            is_target = (nx == target_x and ny == target_y)
            if not is_target and not world.get_tile(nx, ny).is_walkable:
                continue
            # Root-level steps ARE the first direction; every further
            # expansion inherits the ancestor's first direction.
            this_first = (ddx, ddy) if (x, y) == (sx, sy) else first_dir[(x, y)]
            if is_target:
                return this_first
            first_dir[(nx, ny)] = this_first
            queue.append((nx, ny, depth + 1))
    return None


def _bfs_first_reachable(agent, world, predicate):
    """Flood BFS from agent. Return (first_step, target_tile) for the
    nearest walkable tile whose own tile satisfies `predicate`, or
    (None, None) if none reachable within PATH_SEARCH_HORIZON.

    Unlike find_nearest_tile (Manhattan, ignores walkability), this
    pass guarantees the tile is actually reachable — fixes two bugs:
      * Target on an island / behind water → step_toward returned
        None and the agent fell through to random-walk explore
        ("up/down/up/down with food to the left" report).
      * Nearer target gets depleted by another agent → find_nearest
        flipped between ticks → BFS first-step flipped → visible
        oscillation. One flood picks the closest REACHABLE tile
        deterministically (BFS is FIFO on the direction list, so
        ties break consistently across ticks).

    The agent's own tile is not reported back as a target; callers
    should check the own tile separately before invoking this.
    """
    sx, sy = agent.x, agent.y
    first_dir = {(sx, sy): None}
    queue = deque([(sx, sy, 0)])
    while queue:
        x, y, depth = queue.popleft()
        if (x, y) != (sx, sy) and predicate(world.get_tile(x, y)):
            return first_dir[(x, y)], world.get_tile(x, y)
        if depth >= PATH_SEARCH_HORIZON:
            continue
        for ddx, ddy in DIRECTIONS:
            nx, ny = x + ddx, y + ddy
            if (nx, ny) in first_dir:
                continue
            if not world.in_bounds(nx, ny):
                continue
            if not world.get_tile(nx, ny).is_walkable:
                continue
            this_first = (ddx, ddy) if (x, y) == (sx, sy) else first_dir[(x, y)]
            first_dir[(nx, ny)] = this_first
            queue.append((nx, ny, depth + 1))
    return None, None


def step_toward(agent, target_x, target_y, world):
    """Move one tile along a shortest walkable path toward the target.

    Returns True if the agent moved, False if no path exists within
    PATH_SEARCH_HORIZON (caller typically falls back to random walk).

    Historical note: an earlier implementation picked greedily among
    two candidate axes and quit if both were blocked. That produced
    the shoreline-bounce bug where agents one step away from a food
    tile across water would random-walk along the water's edge
    forever, never actually reaching the food.
    """
    step = _first_step_bfs(agent, target_x, target_y, world)
    if step is None:
        return False
    ddx, ddy = step
    nx, ny = agent.x + ddx, agent.y + ddy
    # Defensive: BFS should never return an out-of-bounds first step,
    # but guard anyway so a bad map doesn't crash the tick loop.
    if not world.in_bounds(nx, ny):
        return False
    dest_tile = world.get_tile(nx, ny)
    # Allow stepping ONTO the target tile even if non-walkable; mid-path
    # tiles are already filtered by the BFS.
    is_target = (nx == target_x and ny == target_y)
    if not dest_tile.is_walkable and not is_target:
        return False
    agent.x = nx
    agent.y = ny
    agent.move_cooldown = TERRAIN_MOVE_COST.get(dest_tile.terrain, 1) - 1
    return True


def adjacent_food_tile(agent, world):
    # Own tile counts: an agent standing on food should be able to eat it.
    # Without this check, find_nearest_tile returns the own tile, step_toward
    # has dx=dy=0 so yields no candidates, and the agent falls through to
    # explore — starving on top of food.
    here = world.get_tile(agent.x, agent.y)
    if here.resource_type == 'food' and here.resource_amount > 0:
        return here
    for dx, dy in DIRECTIONS:
        nx, ny = agent.x + dx, agent.y + dy
        if not world.in_bounds(nx, ny):
            continue
        tile = world.get_tile(nx, ny)
        if tile.resource_type == 'food' and tile.resource_amount > 0:
            return tile
    return None


def adjacent_agent(agent, agents):
    # Includes co-located agents (distance 0). Agents legitimately end up
    # sharing a tile (small worlds, random walk converging), and with
    # == 1 they could never socialise out of it — social decayed forever.
    for other in agents:
        if other is agent or not other.alive:
            continue
        if abs(other.x - agent.x) + abs(other.y - agent.y) <= 1:
            return other
    return None


def _forage_yield_from_d20(rng):
    """Roll a d20 and band it onto a forage yield in tile units.

    Banding (avg ≈ 2.0 — matches the prior flat FORAGE_TILE_DEPLETION so
    long-run pacing is unchanged, but with visible variance):

      1     → 0 (crit fail — fumbled)
      2-5   → 1 (low)
      6-15  → 2 (typical)
      16-19 → 3 (good)
      20    → 5 (crit — bumper crop)

    Returns ``(roll, max_yield)``. The caller still clamps against tile
    resource and pouch room — the d20 governs the ceiling, not the floor."""
    roll = rng.randint(1, 20)
    if roll == 1:
        return roll, 0
    if roll <= 5:
        return roll, 1
    if roll <= 15:
        return roll, 2
    if roll <= 19:
        return roll, 3
    return roll, 5


def forage(agent, world, *, rng):
    # Honest-action guard: idle only when BOTH hunger and pouch are
    # full. A sated agent with empty cargo still forages (stockpiling
    # for the colony), and a hungry agent with a full pouch still
    # forages (the gather action feeds their own hunger regardless).
    if agent.hunger >= needs.NEED_MAX and agent.cargo >= needs.CARRY_MAX:
        return {'type': 'idled', 'description': f'{agent.name} was already full on hunger'}
    tile = adjacent_food_tile(agent, world)
    if tile is not None:
        # Taken from the tile is bounded by pouch room AND a d20 roll —
        # an agent with nowhere to put surplus can't drain a tile for
        # nothing, and the dice add narrative variance (a crit-fail
        # forage takes home zero even when the tile is full). Tile
        # units only leave the world through a pouch slot or a mouth.
        pouch_room = needs.CARRY_MAX - agent.cargo
        roll, ceiling = _forage_yield_from_d20(rng)
        taken = min(ceiling, tile.resource_amount, pouch_room)
        tile.resource_amount -= taken
        agent.cargo += taken
        # Hunger fills regardless — the gather action doubles as eating
        # on the spot. The FORAGE_HUNGER_RESTORE constant is independent
        # of `taken` so a tile-starved forage still feeds the agent
        # what little they found.
        agent.hunger = min(needs.NEED_MAX, agent.hunger + needs.FORAGE_HUNGER_RESTORE)
        agent.state = STATE_FORAGING
        return {
            'type': 'foraged',
            'description': f'{agent.name} gathered food at ({tile.x},{tile.y}) (d20={roll})',
            # Structured payload drives the persistence dirty-set: the service
            # updates exactly the tile rows whose amount changed. `roll` rides
            # on the same event so the renderer can flash a dice chip above
            # the foraging agent for narrative feedback.
            'data': {
                'tile_x': tile.x,
                'tile_y': tile.y,
                'amount_taken': taken,
                'roll': roll,
            },
        }

    # BFS flood for the nearest REACHABLE food tile. Previously used
    # find_nearest_tile (Manhattan, ignores walkability) + step_toward
    # (BFS on that target), which failed two ways: unreachable targets
    # dropped to random-walk, and nearer-target-depleted oscillated the
    # chosen target between ticks. The flood resolves both: a single
    # pass returns a reachable target with its first step.
    step, target = _bfs_first_reachable(
        agent, world,
        lambda t: t.resource_type == 'food' and t.resource_amount > 0,
    )
    if step is None:
        return explore(agent, world, rng=rng)

    ddx, ddy = step
    nx, ny = agent.x + ddx, agent.y + ddy
    dest_tile = world.get_tile(nx, ny)
    agent.x = nx
    agent.y = ny
    agent.move_cooldown = TERRAIN_MOVE_COST.get(dest_tile.terrain, 1) - 1
    agent.state = STATE_FORAGING
    return {
        'type': 'moved',
        'description': f'{agent.name} moved toward food at ({target.x},{target.y})',
    }


def rest(agent):
    # Honest-action guard: dawn phase routes full-energy agents here.
    # Without this, we emit a sham 'rested' event (and grant a heal bonus)
    # for an agent that did nothing.
    if agent.energy >= needs.NEED_MAX:
        return {'type': 'idled', 'description': f'{agent.name} was already full on energy'}
    agent.energy = min(needs.NEED_MAX, agent.energy + needs.REST_ENERGY_RESTORE)
    # Rest while well-fed → extra health regen on top of the passive drip
    # in decay_needs. Strict-greater gate matches decay_needs so a single
    # threshold controls "is this agent fed enough to heal."
    if agent.hunger > needs.HUNGER_MODERATE:
        agent.health = min(needs.NEED_MAX, agent.health + needs.REST_HEAL_BONUS)
    agent.state = STATE_RESTING
    return {
        'type': 'rested',
        'description': f'{agent.name} rested',
    }


def rest_outdoors(agent):
    """Field rest — half the energy recovery of rest(), no heal bonus.

    Used when night catches an agent away from camp, or when a rogue
    agent can never return. Encodes "sleeping rough < sleeping home":
    gives enough recovery that field work stays viable but home rest
    remains strictly dominant, so camp-goers retain the advantage."""
    if agent.energy >= needs.NEED_MAX:
        return {'type': 'idled', 'description': f'{agent.name} was already full on energy'}
    agent.energy = min(needs.NEED_MAX, agent.energy + needs.REST_ENERGY_RESTORE * 0.5)
    agent.state = STATE_RESTING
    return {
        'type': 'rested_outdoors',
        'description': f'{agent.name} rested in the open',
    }


def socialise(agent, agents, *, colony):
    """Refill social only when BOTH participants are on the colony's camp tile.

    Rationale (§day-night extension): socialising is a "home fire" ritual,
    not a chance encounter in the field. Social need only tops up when an
    agent returns to camp and finds a colony-mate there too. This forces
    a return loop: long expeditions let social decay → agent must come
    back → if too late, they go rogue."""
    # Honest-action guard: full social → no-op. Emits before the partner
    # lookup so we don't fire a sham 'passed in the field' event either.
    if agent.social >= needs.NEED_MAX:
        return {'type': 'idled', 'description': f'{agent.name} was already full on social'}
    other = adjacent_agent(agent, agents)
    if other is None:
        return {'type': 'idled', 'description': f'{agent.name} found no one to socialise with'}

    at_camp = colony.is_at_camp(agent.x, agent.y) and colony.is_at_camp(other.x, other.y)
    if not at_camp:
        # Neighbours met in the field — no social refill. Still emits
        # an event so the tick log shows the encounter.
        return {
            'type': 'idled',
            'description': f'{agent.name} passed {other.name} in the field',
        }

    agent.social = min(needs.NEED_MAX, agent.social + needs.SOCIALISE_SOCIAL_RESTORE)
    other.social = min(needs.NEED_MAX, other.social + needs.SOCIALISE_SOCIAL_RESTORE)
    agent.state = STATE_SOCIALISING
    return {
        'type': 'socialised',
        'description': f'{agent.name} socialised with {other.name}',
    }


def explore(agent, world, *, rng):
    options = []
    for dx, dy in DIRECTIONS:
        nx, ny = agent.x + dx, agent.y + dy
        if world.in_bounds(nx, ny) and world.get_tile(nx, ny).is_walkable:
            options.append((nx, ny))
    if not options:
        agent.state = STATE_IDLE
        return {'type': 'idled', 'description': f'{agent.name} stayed in place'}
    agent.x, agent.y = rng.choice(options)
    dest_terrain = world.get_tile(agent.x, agent.y).terrain
    agent.move_cooldown = TERRAIN_MOVE_COST.get(dest_terrain, 1) - 1
    agent.state = STATE_EXPLORING
    return {
        'type': 'moved',
        'description': f'{agent.name} moved to ({agent.x},{agent.y})',
    }


def die(agent):
    agent.alive = False
    agent.state = STATE_DEAD
    return {
        'type': 'died',
        'description': f'{agent.name} has died',
    }


def plant(agent, world, colony):
    """Convert the tile under `agent` into a growing crop owned by `colony`.

    Pre-conditions (caller should already have checked via decide_action):
      * tile.crop_state == 'none'
      * tile.resource_amount == 0 (i.e. empty wild)
      * colony.growing_count < config.MAX_FIELDS_PER_COLONY

    This function re-guards all three; a violated pre-condition yields an
    `idled` no-op event so the engine never silently mutates state.
    """
    tile = world.get_tile(agent.x, agent.y)
    if tile.crop_state != 'none':
        return {'type': 'idled', 'description': f'{agent.name} found crop already here'}
    if tile.resource_amount > 0:
        return {'type': 'idled', 'description': f'{agent.name} found wild food here, skipping plant'}
    if colony.growing_count >= config.MAX_FIELDS_PER_COLONY:
        return {'type': 'idled', 'description': f'{agent.name} deferred plant (field cap)'}

    tile.crop_state = 'growing'
    tile.crop_growth_ticks = 0
    tile.crop_colony_id = colony.id
    colony.growing_count += 1
    agent.state = STATE_PLANTING
    return {
        'type': 'planted',
        'description': f'{agent.name} planted at ({tile.x},{tile.y})',
        'data': {
            'tile_x': tile.x,
            'tile_y': tile.y,
            'colony_id': colony.id,
            'agent_id': agent.id,
        },
    }


def harvest(agent, world, colony):
    """Harvest a mature crop under `agent`. Credits `colony` (the harvester).

    The planter's colony is NOT credited — this is the "pure scarcity, no
    ownership" rule from the spec. Any agent can harvest any mature tile
    and the yield goes to their own colony's stock.
    """
    tile = world.get_tile(agent.x, agent.y)
    if tile.crop_state != 'mature':
        return {'type': 'idled', 'description': f'{agent.name} found no mature crop'}

    yield_amount = config.HARVEST_YIELD
    colony.food_stock += yield_amount
    tile.crop_state = 'none'
    tile.crop_growth_ticks = 0
    tile.crop_colony_id = None
    tile.resource_amount = 0
    agent.state = STATE_HARVESTING

    return {
        'type': 'harvested',
        'description': f'{agent.name} harvested ({tile.x},{tile.y}) → +{yield_amount} stock',
        'data': {
            'tile_x': tile.x,
            'tile_y': tile.y,
            'colony_id': colony.id,
            'agent_id': agent.id,
            'yield_amount': yield_amount,
        },
    }


def deposit_cargo(agent, colony):
    """Drop the agent's foraged pouch into the colony's shared stock.

    Pre-conditions:
      * agent standing on the colony's camp tile
      * agent.cargo > 0

    Violations → idled no-op. Success → colony.food_stock bumps by the
    whole cargo value, agent.cargo resets to 0, emits 'deposited' with
    the amount so the UI can flash the feedback.
    """
    if not colony.is_at_camp(agent.x, agent.y):
        return {'type': 'idled', 'description': f'{agent.name} not at camp'}
    if agent.cargo <= 0:
        return {'type': 'idled', 'description': f'{agent.name} has nothing to deposit'}
    amount = agent.cargo
    colony.food_stock += amount
    agent.cargo = 0.0
    agent.state = STATE_DEPOSITING
    return {
        'type': 'deposited',
        'description': f'{agent.name} dropped off {amount:g} food',
        'data': {
            'agent_id': agent.id,
            'colony_id': colony.id,
            'amount': amount,
        },
    }


def eat_cargo(agent):
    """Rogue's larder: consume one pouch unit, bump hunger.

    Rogue agents have no camp to deposit or eat at. Without this action
    a rogue who forages to full cargo can't spend any of it on their
    own hunger — the forage action double-feeds during gather, but once
    the agent is away from food tiles the cargo just sits unused.

    Pre-conditions:
      * agent.cargo > 0
      * agent.hunger < NEED_MAX

    Consumes 1 unit. Hunger bumps by FORAGE_HUNGER_RESTORE — same as
    the gather-time hunger restore so a cargo meal feels like a forage
    meal. Caller (decide_action rogue branch) already gates on
    HUNGER_MODERATE, so the strict-less-than guard here is defensive.
    """
    if agent.cargo <= 0:
        return {'type': 'idled', 'description': f'{agent.name} had nothing in their pouch'}
    if agent.hunger >= needs.NEED_MAX:
        return {'type': 'idled', 'description': f'{agent.name} was already full on hunger'}
    taken = min(1.0, agent.cargo)
    agent.cargo -= taken
    agent.hunger = min(needs.NEED_MAX, agent.hunger + needs.FORAGE_HUNGER_RESTORE)
    agent.state = STATE_EATING
    return {
        'type': 'ate_from_cargo',
        'description': f'{agent.name} ate from their pouch',
        'data': {
            'agent_id': agent.id,
            'amount': taken,
        },
    }


def eat_camp(agent, colony):
    """Dawn meal at camp. Cap-fills hunger, debits colony stock by EAT_COST.

    Pre-conditions:
      * agent on own camp tile
      * colony.food_stock >= EAT_COST
      * agent.hunger < NEED_MAX
      * agent has not already eaten this dawn window

    Violations → idled no-op. Success → cap-fills hunger, emits
    ate_from_cache with amount=EAT_COST, flags agent.ate_this_dawn.
    """
    if not colony.is_at_camp(agent.x, agent.y):
        return {'type': 'idled', 'description': f'{agent.name} not at camp'}
    if colony.food_stock < config.EAT_COST:
        return {'type': 'idled', 'description': f'{agent.name} found empty stock'}
    if agent.hunger >= needs.NEED_MAX:
        return {'type': 'idled', 'description': f'{agent.name} already full'}
    if agent.ate_this_dawn:
        return {'type': 'idled', 'description': f'{agent.name} already ate this dawn'}

    hunger_before = agent.hunger
    agent.hunger = needs.NEED_MAX
    colony.food_stock -= config.EAT_COST
    agent.ate_this_dawn = True
    agent.state = STATE_EATING
    return {
        'type': 'ate_from_cache',
        'description': f'{agent.name} ate at camp',
        'data': {
            'agent_id': agent.id,
            'colony_id': colony.id,
            'amount': config.EAT_COST,
            'hunger_before': hunger_before,
            'hunger_after': agent.hunger,
        },
    }
