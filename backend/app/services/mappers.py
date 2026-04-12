from app import models
from app.engine.agent import Agent as EngineAgent
from app.engine.world import Tile as EngineTile, World as EngineWorld


def agent_to_row(agent):
    return models.Agent(
        id=agent.id,
        name=agent.name,
        x=agent.x,
        y=agent.y,
        state=agent.state,
        hunger=agent.hunger,
        energy=agent.energy,
        social=agent.social,
        health=agent.health,
        age=agent.age,
        alive=agent.alive,
    )


def row_to_agent(row):
    a = EngineAgent(name=row.name, x=row.x, y=row.y, agent_id=row.id)
    a.state = row.state
    a.hunger = row.hunger
    a.energy = row.energy
    a.social = row.social
    a.health = row.health
    a.age = row.age
    a.alive = row.alive
    return a


def update_agent_row(row, engine_agent):
    """Copy mutable per-tick fields from engine agent onto its ORM row.
    `name` and `id` are immutable post-spawn — omit them.
    """
    row.x = engine_agent.x
    row.y = engine_agent.y
    row.state = engine_agent.state
    row.hunger = engine_agent.hunger
    row.energy = engine_agent.energy
    row.social = engine_agent.social
    row.health = engine_agent.health
    row.age = engine_agent.age
    row.alive = engine_agent.alive


def tile_to_row(tile):
    return models.WorldTile(
        x=tile.x,
        y=tile.y,
        terrain=tile.terrain,
        resource_type=tile.resource_type,
        resource_amount=tile.resource_amount,
    )


def tile_to_row_mapping(tile):
    # Legacy dict form, retained only for audit/bug5_n_flush.py and
    # audit/bug6_no_rollback.py which reproduce the pre-fix bulk_insert_mappings
    # shape. The live service now goes through tile_to_row + add_all.
    return {
        'x': tile.x,
        'y': tile.y,
        'terrain': tile.terrain,
        'resource_type': tile.resource_type,
        'resource_amount': tile.resource_amount,
    }


def row_to_tile(row):
    return EngineTile(
        x=row.x,
        y=row.y,
        terrain=row.terrain,
        resource_type=row.resource_type,
        resource_amount=row.resource_amount,
    )


def update_tile_row(row, engine_tile):
    """Only resource_amount is mutable post-generation (drops on forage).
    Terrain/coords are immutable for a given world.
    """
    row.resource_amount = engine_tile.resource_amount


def rows_to_world(tile_rows, width, height):
    """Rebuild a World from tile rows. Rows may arrive in any order."""
    world = EngineWorld(width, height)
    world.tiles = [[None] * width for _ in range(height)]
    for row in tile_rows:
        world.tiles[row.y][row.x] = row_to_tile(row)
    # Invariant: every cell is filled. If any is None, the row set is
    # incomplete relative to (width, height) — corrupt persisted state.
    for y, row_cells in enumerate(world.tiles):
        for x, cell in enumerate(row_cells):
            if cell is None:
                raise ValueError(
                    f'missing tile at ({x},{y}) while rebuilding {width}x{height} world'
                )
    return world


def event_to_row(event):
    return models.Event(
        tick=event['tick'],
        agent_id=event.get('agent_id'),
        event_type=event['type'],
        description=event.get('description'),
        data=event.get('data'),
    )


def events_to_row_mappings(events):
    return [
        {
            'tick': e['tick'],
            'agent_id': e.get('agent_id'),
            'event_type': e['type'],
            'description': e.get('description'),
            'data': e.get('data'),
        }
        for e in events
    ]
