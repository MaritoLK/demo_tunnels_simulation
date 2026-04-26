from datetime import datetime, timezone

from app import db


class Agent(db.Model):
    __tablename__ = 'agents'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    x = db.Column(db.Integer, nullable=False)
    y = db.Column(db.Integer, nullable=False)
    state = db.Column(db.String(20), nullable=False, default='idle', server_default='idle')
    hunger = db.Column(db.Float, nullable=False, default=100.0, server_default='100.0')
    energy = db.Column(db.Float, nullable=False, default=100.0, server_default='100.0')
    social = db.Column(db.Float, nullable=False, default=100.0, server_default='100.0')
    health = db.Column(db.Float, nullable=False, default=100.0, server_default='100.0')
    age = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    alive = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    cargo = db.Column(db.Float, nullable=False, default=0.0, server_default='0.0')
    colony_id = db.Column(
        db.Integer,
        db.ForeignKey('colonies.id', ondelete='SET NULL'),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=db.func.now(),
    )

    __table_args__ = (
        db.Index('idx_agents_position', 'x', 'y'),
        db.Index('idx_agents_alive', 'alive', postgresql_where=db.text('alive = TRUE')),
    )
