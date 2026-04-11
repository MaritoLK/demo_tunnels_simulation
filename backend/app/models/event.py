from datetime import datetime, timezone
from app import db


class Event(db.Model):
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    tick = db.Column(db.Integer, nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=True)
    event_type = db.Column(db.String(30), nullable=False)
    description = db.Column(db.Text, nullable=True)
    data = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
