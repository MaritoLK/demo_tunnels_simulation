"""Task 1 model-layer tests.

Cover the load-bearing invariants of the 6 new foundation models:
  * GameStateRow singleton (CHECK id=1) — positive + rejection
  * NPC JSONB roundtrip
  * EventLog append-only write
  * SaveMeta defaults + explicit-seed requirement
  * Policy JSONB roundtrip
  * Relationship canonical-order CHECK (rejection)

Deliberately out of scope for Task 1 (will land with their first real
consumer in later tasks): FK cascade tests, index presence assertions,
and FK-requires-both-ends tests.
"""
import pytest
import sqlalchemy

from app import db
from app.models.event_log import EventLog
from app.models.game_state_row import GameStateRow
from app.models.npc import NPC
from app.models.policy import Policy
from app.models.relationship import Relationship
from app.models.save_meta import SaveMeta


def test_game_state_row_singleton(client):
    row = GameStateRow(
        id=1, tick=0, year=0, active_layer='life_sim',
        alignment_axes_json={'dictator_benefactor': 0},
    )
    db.session.add(row)
    db.session.commit()

    got = db.session.get(GameStateRow, 1)
    assert got.active_layer == 'life_sim'
    assert got.alignment_axes_json == {'dictator_benefactor': 0}


def test_npc_roundtrip(client):
    n = NPC(
        tier=1, name='Aldric',
        stats_json={'competence': 3, 'loyalty': 4},
        memory_json=[], status='alive',
    )
    db.session.add(n)
    db.session.commit()

    got = NPC.query.filter_by(name='Aldric').first()
    assert got is not None
    assert got.stats_json['competence'] == 3
    assert got.memory_json == []
    assert got.status == 'alive'


def test_event_log_append_only(client):
    e = EventLog(
        tick=1, tier='P2', source_id=1, source_type='councilor',
        payload_json={'kind': 'drama', 'text': 'Steward grumbled'},
    )
    db.session.add(e)
    db.session.commit()

    assert EventLog.query.count() == 1


def test_game_state_singleton_rejects_second_row(client):
    first = GameStateRow(
        id=1, tick=0, year=0, active_layer='life_sim',
        alignment_axes_json={},
    )
    db.session.add(first)
    db.session.commit()

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        second = GameStateRow(
            id=2, tick=0, year=0, active_layer='life_sim',
            alignment_axes_json={},
        )
        db.session.add(second)
        db.session.commit()
    db.session.rollback()


def test_save_meta_defaults(client):
    # seed=0 is a VALID seed; passing it explicitly proves the NOT-NULL
    # is satisfied by explicit provision, not by a default.
    meta = SaveMeta(id=1, seed=0)
    db.session.add(meta)
    db.session.commit()

    got = db.session.get(SaveMeta, 1)
    assert got.schema_version == 1
    assert got.gen_number == 1
    assert got.playtime_seconds == 0
    assert got.seed == 0


def test_policy_roundtrip(client):
    p = Policy(name='tax', effects_json={'rate': 0.1}, active_until_tick=100)
    db.session.add(p)
    db.session.commit()

    got = Policy.query.filter_by(name='tax').first()
    assert got is not None
    assert got.effects_json['rate'] == 0.1
    assert got.active_until_tick == 100


def test_relationship_rejects_non_canonical_order(client):
    a = NPC(tier=1, name='A', stats_json={}, memory_json=[], status='alive')
    b = NPC(tier=1, name='B', stats_json={}, memory_json=[], status='alive')
    db.session.add_all([a, b])
    db.session.flush()  # assign IDs without committing

    low, high = sorted([a.id, b.id])

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        bad = Relationship(
            npc_a_id=high, npc_b_id=low, type='spouse', strength=0,
        )
        db.session.add(bad)
        db.session.commit()
    db.session.rollback()
