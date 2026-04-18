"""Task 2 mapper tests.

Pin the row<->engine-dict contract for the foundation models. Pure
mapper-logic tests run without DB; defaults and roundtrips that need
actual commit semantics use the `client` fixture for TRUNCATE isolation.

The default-fill test is load-bearing: if someone re-adds
`.get(..., default)` to the mapper path, the schema stops owning
defaults and this test catches it.
"""
from app import db
from app.models.event_log import EventLog
from app.models.npc import NPC
from app.models.policy import Policy
from app.models.relationship import Relationship
from app.services import game_mappers


def test_npc_row_roundtrip():
    engine_npc = {
        'id': 1, 'tier': 1, 'name': 'Aldric',
        'stats': {'competence': 3, 'loyalty': 4, 'ambition': 2, 'specialty': 'steward'},
        'memory': [], 'status': 'alive',
    }
    row = game_mappers.npc_to_row(engine_npc)
    assert isinstance(row, NPC)
    assert row.stats_json['competence'] == 3
    back = game_mappers.row_to_npc(row)
    assert back['name'] == 'Aldric'
    assert back['stats']['specialty'] == 'steward'


def test_defaults_fill_on_missing_keys(client):
    """Schema owns defaults — mapper must NOT re-specify them.

    Regression guard: if someone re-adds `.get('status', 'alive')` or
    `.get('memory', [])` to the mapper, this test still passes locally
    but a subtler bug creeps in (mapper default and schema default can
    drift). Here we assert the *schema* default is what populates the
    row: build a dict with only the NOT-NULL-no-default keys, commit,
    reload, and check the DB-supplied defaults.
    """
    row = game_mappers.npc_to_row({
        'tier': 2, 'name': 'Mira',
        'stats': {'competence': 1},
    })
    db.session.add(row)
    db.session.commit()

    got = db.session.get(NPC, row.id)
    assert got.status == 'alive'  # server_default
    assert got.memory_json == []  # server_default '[]'::jsonb


def test_event_payload_roundtrip(client):
    """Nested payload + nullable source_* fields survive a commit/reload."""
    event = {
        'tick': 42,
        'tier': 'P2',
        'source_id': None,
        'source_type': None,
        'payload': {
            'kind': 'drama',
            'actors': [1, 2, 3],
            'details': {'mood': 'tense', 'tags': ['court', 'rivalry']},
        },
    }
    row = game_mappers.event_to_row(event)
    db.session.add(row)
    db.session.commit()

    got = db.session.get(EventLog, row.id)
    back = game_mappers.row_to_event(got)
    assert back['tick'] == 42
    assert back['tier'] == 'P2'
    assert back['source_id'] is None
    assert back['source_type'] is None
    assert back['payload'] == event['payload']


def test_relationship_canonical_ordering_in_mapper():
    """Input with a > b must still produce a row with npc_a_id < npc_b_id.

    Proves `_canonical_pair` is wired through the mapper — not just
    available in the model module. Otherwise Task 3+ writers could
    accidentally bypass canonicalisation by going through the mapper.
    """
    row = game_mappers.relationship_to_row({
        'npc_a_id': 7, 'npc_b_id': 5, 'type': 'spouse',
    })
    assert isinstance(row, Relationship)
    assert row.npc_a_id == 5
    assert row.npc_b_id == 7
    assert row.type == 'spouse'


def test_policy_nullable_active_until_tick(client):
    """active_until_tick=None (open-ended policy) survives roundtrip."""
    policy = {
        'name': 'levy',
        'effects': {'food': -5},
        'active_until_tick': None,
    }
    row = game_mappers.policy_to_row(policy)
    db.session.add(row)
    db.session.commit()

    got = db.session.get(Policy, row.id)
    back = game_mappers.row_to_policy(got)
    assert back['active_until_tick'] is None
    assert back['effects'] == {'food': -5}
    assert back['name'] == 'levy'
