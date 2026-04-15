"""Action functions. Each returns an event dict and mutates the agent / world.

Pure Python — no Flask, no DB imports. Safe to unit-test without fixtures.

Any action that consumes randomness takes `rng` as a keyword-only required
argument — no silent fallback to the `random` module. The engine's
reproducibility contract (sub-seeded rng_spawn / rng_tick, see §9.11) is
only useful if every caller threads rng through; enforcing it at the
signature makes the contract impossible to bypass by accident.
"""
from . import needs


DIRECTIONS = [(0, 1), (0, -1), (1, 0), (-1, 0)]

STATE_IDLE = 'idle'
STATE_RESTING = 'resting'
STATE_FORAGING = 'foraging'
STATE_SOCIALISING = 'socialising'
STATE_EXPLORING = 'exploring'
STATE_DEAD = 'dead'


def step_toward(agent, target_x, target_y, world):
    dx = target_x - agent.x
    dy = target_y - agent.y
    candidates = []
    if abs(dx) >= abs(dy):
        if dx != 0:
            candidates.append((1 if dx > 0 else -1, 0))
        if dy != 0:
            candidates.append((0, 1 if dy > 0 else -1))
    else:
        if dy != 0:
            candidates.append((0, 1 if dy > 0 else -1))
        if dx != 0:
            candidates.append((1 if dx > 0 else -1, 0))

    for ddx, ddy in candidates:
        nx, ny = agent.x + ddx, agent.y + ddy
        if world.in_bounds(nx, ny) and world.get_tile(nx, ny).is_walkable:
            agent.x = nx
            agent.y = ny
            return True
    return False


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


def forage(agent, world, *, rng):
    tile = adjacent_food_tile(agent, world)
    if tile is not None:
        taken = min(needs.FORAGE_TILE_DEPLETION, tile.resource_amount)
        tile.resource_amount -= taken
        agent.hunger = min(needs.NEED_MAX, agent.hunger + needs.FORAGE_HUNGER_RESTORE)
        agent.state = STATE_FORAGING
        return {
            'type': 'foraged',
            'description': f'{agent.name} gathered food at ({tile.x},{tile.y})',
            # Structured payload drives the persistence dirty-set: the service
            # updates exactly the tile rows whose amount changed.
            'data': {
                'tile_x': tile.x,
                'tile_y': tile.y,
                'amount_taken': taken,
            },
        }

    target = world.find_nearest_tile(
        agent.x, agent.y,
        lambda t: t.resource_type == 'food' and t.resource_amount > 0,
    )
    if target is None:
        return explore(agent, world, rng=rng)

    moved = step_toward(agent, target.x, target.y, world)
    if not moved:
        # greedy step blocked (no pathfinding); random walk so agent at least moves
        return explore(agent, world, rng=rng)
    agent.state = STATE_FORAGING
    return {
        'type': 'moved',
        'description': f'{agent.name} moved toward food at ({target.x},{target.y})',
    }


def rest(agent):
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


def socialise(agent, agents):
    other = adjacent_agent(agent, agents)
    if other is None:
        return {'type': 'idled', 'description': f'{agent.name} found no one to socialise with'}
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
    from . import config
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
    return {
        'type': 'planted',
        'description': f'{agent.name} planted at ({tile.x},{tile.y})',
        'data': {'tile_x': tile.x, 'tile_y': tile.y, 'colony_id': colony.id},
    }
