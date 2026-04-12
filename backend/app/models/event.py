from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import JSONB

from app import db


class Event(db.Model):
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    tick = db.Column(db.Integer, nullable=False)
    agent_id = db.Column(
        db.Integer,
        # RESTRICT, not SET NULL: agents are soft-deleted via alive=false,
        # never hard-deleted. A cascade to NULL here would silently erase
        # the attribution of historical events for a deleted agent, which
        # defeats the whole point of an audit log.
        db.ForeignKey('agents.id', ondelete='RESTRICT'),
        nullable=True,
    )
    event_type = db.Column(db.String(30), nullable=False)
    description = db.Column(db.Text, nullable=True)
    data = db.Column(JSONB, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=db.func.now(),
    )

    __table_args__ = (
        # Composite (agent_id, tick) serves the per-agent timeline read
        # pattern — WHERE agent_id = ? ORDER BY tick — as a single index
        # scan without a sort. The composite prefix also covers the
        # agent_id-only filter, so no standalone agent_id index is needed.
        db.Index('idx_events_agent_tick', 'agent_id', 'tick'),
        db.Index('idx_events_tick', 'tick'),
    )
