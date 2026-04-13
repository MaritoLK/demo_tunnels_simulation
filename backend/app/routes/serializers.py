"""Wire-format translators: engine/ORM objects → JSON-safe dicts.

Kept deliberately thin and stateless. Flask 2.x auto-JSON-ifies returned
dicts, so routes just build and return these directly.

Field renames happen here (not in the engine or models):
  * Event DB column `event_type` is exposed on the wire as `type` —
    matches the engine's internal event key and keeps the REST surface
    consistent with what clients see in the `/step` response.
"""


def agent_to_dict(agent):
    return {
        'id': agent.id,
        'name': agent.name,
        'x': agent.x,
        'y': agent.y,
        'state': agent.state,
        'hunger': agent.hunger,
        'energy': agent.energy,
        'social': agent.social,
        'health': agent.health,
        'age': agent.age,
        'alive': agent.alive,
    }


def tile_to_dict(tile):
    return {
        'x': tile.x,
        'y': tile.y,
        'terrain': tile.terrain,
        'resource_type': tile.resource_type,
        'resource_amount': tile.resource_amount,
    }


def world_to_dict(world):
    """Return the world as a 2-D grid indexed [y][x] matching engine layout."""
    return {
        'width': world.width,
        'height': world.height,
        'tiles': [[tile_to_dict(t) for t in row] for row in world.tiles],
    }


def simulation_summary(sim, control):
    """Wire summary combining engine state (tick, agent counts) with the
    DB-backed control flags (running, speed). `control` is the dict returned
    by `simulation_service.get_simulation_control()` — passing it in rather
    than re-reading here keeps this serializer pure and the DB touch in
    one place.
    """
    return {
        'tick': sim.current_tick,
        'seed': sim.seed,
        'width': sim.world.width,
        'height': sim.world.height,
        'agent_count': len(sim.agents),
        'alive_count': len(sim.alive_agents),
        'running': control['running'],
        'speed': control['speed'],
    }


def engine_event_to_dict(event):
    """Live engine event (as returned by Simulation.step/run)."""
    return {
        'tick': event['tick'],
        'agent_id': event.get('agent_id'),
        'type': event['type'],
        'description': event.get('description'),
        'data': event.get('data'),
    }


def event_row_to_dict(row):
    """Persisted event row. Note column `event_type` renames to `type`."""
    return {
        'tick': row.tick,
        'agent_id': row.agent_id,
        'type': row.event_type,
        'description': row.description,
        'data': row.data,
    }
