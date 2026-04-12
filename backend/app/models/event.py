from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import JSONB

from app import db


class Event(db.Model):
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    tick = db.Column(db.Integer, nullable=False)
    agent_id = db.Column(
        db.Integer,
        db.ForeignKey('agents.id', ondelete='SET NULL'),
        nullable=True,
    )
    event_type = db.Column(db.String(30), nullable=False)
    description = db.Column(db.Text, nullable=True)
    data = db.Column(JSONB, nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        server_default=db.func.now(),
    )

    __table_args__ = (
        db.Index('idx_events_tick', 'tick'),
        db.Index('idx_events_agent_id', 'agent_id'),
        db.Index('idx_events_event_type', 'event_type'),
    )
