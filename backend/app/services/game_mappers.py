"""Row<->engine-dict conversions for game foundation models.

Keep these pure (no db.session access) — service layer owns commits.

Conventions:
- JSON columns use the `_json` suffix at the column level; engine dict keys
  are unsuffixed (stats_json <-> stats, payload_json <-> payload,
  memory_json <-> memory, effects_json <-> effects,
  alignment_axes_json <-> alignment_axes).
- Defaults are owned by the schema (server_default + ORM default).
  Mappers do NOT re-specify defaults; missing keys fall through to DB.
- NOT NULL columns with no default (e.g. SaveMeta.seed) raise KeyError
  on missing input — caller must be explicit.
"""
from app.models.event_log import EventLog
from app.models.game_state_row import GameStateRow
from app.models.npc import NPC
from app.models.policy import Policy
from app.models.relationship import Relationship, _canonical_pair
from app.models.save_meta import SaveMeta


# --- NPC ---------------------------------------------------------------

def npc_to_row(npc: dict) -> NPC:
    # Only forward keys that are actually present. Passing a column as
    # None would send NULL to Postgres and bypass server_default — the
    # schema can only apply its default when the column is omitted from
    # the INSERT altogether (see D4: defaults owned by schema).
    kwargs = {
        'tier': npc['tier'],
        'name': npc['name'],
        'stats_json': npc['stats'],
    }
    if 'id' in npc:
        kwargs['id'] = npc['id']
    if 'memory' in npc:
        kwargs['memory_json'] = npc['memory']
    if 'status' in npc:
        kwargs['status'] = npc['status']
    return NPC(**kwargs)


def row_to_npc(row: NPC) -> dict:
    return {
        'id': row.id,
        'tier': row.tier,
        'name': row.name,
        'stats': row.stats_json,
        'memory': row.memory_json,
        'status': row.status,
    }


def update_npc_row(row: NPC, npc: dict) -> None:
    row.stats_json = npc['stats']
    if 'memory' in npc:
        row.memory_json = npc['memory']
    if 'status' in npc:
        row.status = npc['status']


# --- EventLog (append-only; no update fn) ------------------------------

def event_to_row(event: dict) -> EventLog:
    # source_id / source_type ARE nullable (True nullable columns, not
    # defaulted), so explicit None is fine. payload_json has a
    # server_default — omit it if missing rather than sending NULL.
    kwargs = {
        'tick': event['tick'],
        'tier': event['tier'],
        'source_id': event.get('source_id'),
        'source_type': event.get('source_type'),
    }
    if 'payload' in event:
        kwargs['payload_json'] = event['payload']
    return EventLog(**kwargs)


def row_to_event(row: EventLog) -> dict:
    return {
        'id': row.id,
        'tick': row.tick,
        'tier': row.tier,
        'source_id': row.source_id,
        'source_type': row.source_type,
        'payload': row.payload_json,
    }


# --- Policy ------------------------------------------------------------

def policy_to_row(policy: dict) -> Policy:
    # active_until_tick is nullable (None = open-ended policy), so pass
    # explicit None. effects_json is the only default-backed column and
    # callers always supply 'effects' (it's the core payload), so no
    # omit-on-missing gymnastics here.
    return Policy(
        id=policy.get('id'),
        name=policy['name'],
        effects_json=policy['effects'],
        active_until_tick=policy.get('active_until_tick'),
    )


def row_to_policy(row: Policy) -> dict:
    return {
        'id': row.id,
        'name': row.name,
        'effects': row.effects_json,
        'active_until_tick': row.active_until_tick,
    }


# --- Relationship ------------------------------------------------------

def relationship_to_row(rel: dict) -> Relationship:
    a, b = _canonical_pair(rel['npc_a_id'], rel['npc_b_id'])
    kwargs = {'npc_a_id': a, 'npc_b_id': b, 'type': rel['type']}
    if 'strength' in rel:
        kwargs['strength'] = rel['strength']
    return Relationship(**kwargs)


def row_to_relationship(row: Relationship) -> dict:
    return {
        'id': row.id,
        'npc_a_id': row.npc_a_id,
        'npc_b_id': row.npc_b_id,
        'type': row.type,
        'strength': row.strength,
    }


# --- SaveMeta ----------------------------------------------------------

def save_meta_to_row(meta: dict) -> SaveMeta:
    # seed is NOT NULL with no server_default — intentional KeyError if
    # missing so callers must be explicit (a zero seed is a valid seed,
    # but a silently-defaulted seed is a silent save-corruption bug).
    # schema_version / playtime_seconds / gen_number have server_defaults —
    # omit on absence so the schema's default lands.
    kwargs = {'seed': meta['seed']}
    for src_key, col in (
        ('schema_version', 'schema_version'),
        ('playtime_seconds', 'playtime_seconds'),
        ('gen_number', 'gen_number'),
    ):
        if src_key in meta:
            kwargs[col] = meta[src_key]
    return SaveMeta(**kwargs)


def row_to_save_meta(row: SaveMeta) -> dict:
    return {
        'id': row.id,
        'schema_version': row.schema_version,
        'playtime_seconds': row.playtime_seconds,
        'gen_number': row.gen_number,
        'seed': row.seed,
    }


# --- GameStateRow (singleton) ------------------------------------------

def state_to_row(state: dict) -> GameStateRow:
    # All non-id columns have server_defaults — omit any missing key so
    # the schema default lands instead of NULL.
    kwargs = {'id': 1}
    for src_key, col in (
        ('tick', 'tick'),
        ('year', 'year'),
        ('active_layer', 'active_layer'),
        ('alignment_axes', 'alignment_axes_json'),
    ):
        if src_key in state:
            kwargs[col] = state[src_key]
    return GameStateRow(**kwargs)


def row_to_state(row: GameStateRow) -> dict:
    return {
        'tick': row.tick,
        'year': row.year,
        'active_layer': row.active_layer,
        'alignment_axes': row.alignment_axes_json,
    }


def update_state_row(row: GameStateRow, state: dict) -> None:
    row.tick = state['tick']
    row.year = state['year']
    row.active_layer = state['active_layer']
    row.alignment_axes_json = state['alignment_axes']
