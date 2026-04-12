from . import needs


DIRECTIONS = [(0, 1), (0, -1), (1, 0), (-1, 0)]


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
    for dx, dy in DIRECTIONS:
        nx, ny = agent.x + dx, agent.y + dy
        if not world.in_bounds(nx, ny):
            continue
        tile = world.get_tile(nx, ny)
        if tile.resource_type == 'food' and tile.resource_amount > 0:
            return tile
    return None


def adjacent_agent(agent, agents):
    for other in agents:
        if other is agent or not other.alive:
            continue
        if abs(other.x - agent.x) + abs(other.y - agent.y) == 1:
            return other
    return None


def forage(agent, world):
    tile = adjacent_food_tile(agent, world)
    if tile is not None:
        taken = min(needs.FORAGE_TILE_DEPLETION, tile.resource_amount)
        tile.resource_amount -= taken
        agent.hunger = min(needs.NEED_MAX, agent.hunger + needs.FORAGE_HUNGER_RESTORE)
        agent.state = 'foraging'
        return {
            'type': 'foraged',
            'description': f'{agent.name} gathered food at ({tile.x},{tile.y})',
        }

    target = world.find_nearest_tile(
        agent.x, agent.y,
        lambda t: t.resource_type == 'food' and t.resource_amount > 0,
    )
    if target is None:
        return explore(agent, world)

    moved = step_toward(agent, target.x, target.y, world)
    agent.state = 'foraging'
    return {
        'type': 'moved',
        'description': f'{agent.name} moved toward food at ({target.x},{target.y})' if moved
        else f'{agent.name} blocked on route to food',
    }


def rest(agent):
    agent.energy = min(needs.NEED_MAX, agent.energy + needs.REST_ENERGY_RESTORE)
    agent.state = 'resting'
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
    agent.state = 'socialising'
    return {
        'type': 'socialised',
        'description': f'{agent.name} socialised with {other.name}',
    }


def explore(agent, world, rng=None):
    import random
    rng = rng or random
    options = []
    for dx, dy in DIRECTIONS:
        nx, ny = agent.x + dx, agent.y + dy
        if world.in_bounds(nx, ny) and world.get_tile(nx, ny).is_walkable:
            options.append((nx, ny))
    if not options:
        agent.state = 'idle'
        return {'type': 'idled', 'description': f'{agent.name} stayed in place'}
    agent.x, agent.y = rng.choice(options)
    agent.state = 'exploring'
    return {
        'type': 'moved',
        'description': f'{agent.name} moved to ({agent.x},{agent.y})',
    }


def die(agent):
    agent.alive = False
    agent.state = 'dead'
    return {
        'type': 'died',
        'description': f'{agent.name} has died',
    }
