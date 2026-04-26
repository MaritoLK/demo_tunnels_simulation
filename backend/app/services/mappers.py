from app import models
from app.engine.agent import Agent as EngineAgent
from app.engine.colony import EngineColony
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
        rogue=agent.rogue,
        loner=agent.loner,
        colony_id=agent.colony_id,
        cargo=agent.cargo,
        tiles_walked=agent.tiles_walked,
    )


def row_to_agent(row):
    a = EngineAgent(name=row.name, x=row.x, y=row.y, agent_id=row.id, colony_id=row.colony_id)
    a.state = row.state
    a.hunger = row.hunger
    a.energy = row.energy
    a.social = row.social
    a.health = row.health
    a.age = row.age
    a.alive = row.alive
    a.rogue = row.rogue
    a.loner = row.loner
    a.cargo = row.cargo
    a.tiles_walked = row.tiles_walked
    return a


def update_agent_row(row, engine_agent):
    """Copy mutable per-tick fields from engine agent onto its ORM row.
    `name` and `id` are immutable post-spawn — omit them.
    `colony_id` is immutable post-spawn — omit it.
    `loner` is immutable post-spawn (set once at sim build) — but copying
    it is a one-way no-op rather than a guard, so keeping the assignment
    here means a future tick path that flips it would survive a step.
    `rogue` is one-way (False → True in decay_needs) and changes per tick.
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
    row.rogue = engine_agent.rogue
    row.loner = engine_agent.loner
    row.cargo = engine_agent.cargo
    row.tiles_walked = engine_agent.tiles_walked


def tile_to_row(tile):
    return models.WorldTile(
        x=tile.x,
        y=tile.y,
        terrain=tile.terrain,
        resource_type=tile.resource_type,
        resource_amount=tile.resource_amount,
        crop_state=tile.crop_state,
        crop_growth_ticks=tile.crop_growth_ticks,
        crop_colony_id=tile.crop_colony_id,
    )


def row_to_tile(row):
    return EngineTile(
        x=row.x,
        y=row.y,
        terrain=row.terrain,
        resource_type=row.resource_type,
        resource_amount=row.resource_amount,
        crop_state=row.crop_state,
        crop_growth_ticks=row.crop_growth_ticks,
        crop_colony_id=row.crop_colony_id,
    )


def update_tile_row(row, engine_tile):
    """Resource_amount is mutable post-generation (drops on forage).
    Crop fields are mutable post-planting (growth ticks increment, state/colony change on harvest).
    Terrain/coords are immutable for a given world.
    """
    row.resource_amount = engine_tile.resource_amount
    row.crop_state = engine_tile.crop_state
    row.crop_growth_ticks = engine_tile.crop_growth_ticks
    row.crop_colony_id = engine_tile.crop_colony_id


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


def colony_to_row(c):
    """Convert an EngineColony to a models.Colony ORM row."""
    return models.Colony(
        id=c.id,
        name=c.name,
        color=c.color,
        camp_x=c.camp_x,
        camp_y=c.camp_y,
        food_stock=c.food_stock,
        sprite_palette=c.sprite_palette,
    )


def row_to_colony(row):
    """Convert a models.Colony ORM row to an EngineColony."""
    return EngineColony(
        id=row.id,
        name=row.name,
        color=row.color,
        camp_x=row.camp_x,
        camp_y=row.camp_y,
        food_stock=row.food_stock,
        sprite_palette=row.sprite_palette,
    )


def update_colony_row(row, engine_colony):
    """Copy mutable per-tick fields from engine colony onto its ORM row.
    Only food_stock changes during simulation; all other fields are immutable post-creation.
    """
    row.food_stock = engine_colony.food_stock
