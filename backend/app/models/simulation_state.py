from datetime import datetime, timezone

from app import db


class SimulationState(db.Model):
    __tablename__ = 'simulation_state'

    id = db.Column(db.Integer, primary_key=True)
    current_tick = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    running = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    speed = db.Column(db.Float, nullable=False, default=1.0, server_default='1.0')
    world_width = db.Column(db.Integer, nullable=False)
    world_height = db.Column(db.Integer, nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        server_default=db.func.now(),
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=db.func.now(),
    )
