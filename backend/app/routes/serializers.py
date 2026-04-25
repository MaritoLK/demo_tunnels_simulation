"""Wire-format translators: engine/ORM objects → JSON-safe dicts.

Pure transformations: every field on the wire is computed from the
function arguments, no module-level state, no service reach-through.
Wall-clock fields (`server_time_ms`, `tick_ms`) arrive via the `time`
parameter — the caller (route or tick_loop) decides when to sample.
Flask 2.x auto-JSON-ifies returned dicts, so routes just build and
return these directly.

Field renames happen here (not in the engine or models):
  * Event DB column `event_type` is exposed on the wire as `type` —
    matches the engine's internal event key and keeps the REST surface
    consistent with what clients see in the `/step` response.
  * Engine slot `Agent.last_decision_reason` is exposed on the wire as
    `decision_reason` — internal name describes when it's set ("last");
    wire name describes what it is. See agent.py:69 for the slot default.
"""
from app.engine import cycle


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
        'colony_id': agent.colony_id,
        'rogue': agent.rogue,
        'loner': agent.loner,
        'cargo': agent.cargo,
        'decision_reason': agent.last_decision_reason,
    }


def tile_to_dict(tile):
    return {
        'x': tile.x,
        'y': tile.y,
        'terrain': tile.terrain,
        'resource_type': tile.resource_type,
        'resource_amount': tile.resource_amount,
        'crop_state': tile.crop_state,
        'crop_growth_ticks': tile.crop_growth_ticks,
        'crop_colony_id': tile.crop_colony_id,
    }


def colony_to_dict(colony):
    return {
        'id': colony.id,
        'name': colony.name,
        'color': colony.color,
        'camp_x': colony.camp_x,
        'camp_y': colony.camp_y,
        'food_stock': colony.food_stock,
        'growing_count': colony.growing_count,
        'sprite_palette': colony.sprite_palette,
    }


def world_to_dict(world):
    """Return the world as a 2-D grid indexed [y][x] matching engine layout."""
    return {
        'width': world.width,
        'height': world.height,
        'tiles': [[tile_to_dict(t) for t in row] for row in world.tiles],
    }


def simulation_summary(sim, control, time):
    """Wire summary combining engine state (tick, agent counts), DB-backed
    control flags (running, speed), and wall-clock fields.

    All three inputs are passed in by the caller — this function reads
    nothing from module-level state. `control` comes from
    `simulation_service.get_simulation_control()`; `time` from
    `simulation_service.time_snapshot()`. Caller-supplied arguments
    keep the serializer pure and the time + DB touches in one place.
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
        'day': cycle.day_for(sim.current_tick),
        'phase': cycle.phase_for(sim.current_tick),
        'server_time_ms': time['server_time_ms'],
        'tick_ms': time['tick_ms'],
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
