from sqlalchemy.dialects.postgresql import JSONB

from app import db


class EventLog(db.Model):
    """Append-only engine event journal.

    `tier` is one of P0 / P1 / P2 / P3 (spec §2 alert tiers), enforced by
    CHECK. `source_type` is free-form String(16); current producers use
    'councilor', 'policy', 'system'. No CHECK on source_type — intent is
    conveyed by migration discipline + tests, not the schema, so adding
    new sources in later tasks doesn't require a schema migration.
    """

    __tablename__ = 'event_log'

    id = db.Column(db.BigInteger, primary_key=True)
    tick = db.Column(db.Integer, nullable=False)
    tier = db.Column(db.String(4), nullable=False)  # P0 / P1 / P2 / P3
    source_id = db.Column(db.Integer, nullable=True)
    source_type = db.Column(db.String(16), nullable=True)  # 'councilor' / 'policy' / 'system'
    payload_json = db.Column(
        JSONB, nullable=False, default=dict, server_default=db.text("'{}'::jsonb"),
    )

    __table_args__ = (
        db.CheckConstraint(
            "tier IN ('P0','P1','P2','P3')", name='event_log_tier_valid',
        ),
        db.Index('idx_event_log_source', 'source_id', 'source_type'),
        db.Index('idx_event_log_tick_tier', 'tick', 'tier'),
    )
