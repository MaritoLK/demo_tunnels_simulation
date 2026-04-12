from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import JSONB

from app import db


class SimulationState(db.Model):
    __tablename__ = 'simulation_state'

    id = db.Column(db.Integer, primary_key=True)
    current_tick = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    running = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    speed = db.Column(db.Float, nullable=False, default=1.0, server_default='1.0')
    world_width = db.Column(db.Integer, nullable=False)
    world_height = db.Column(db.Integer, nullable=False)
    seed = db.Column(db.BigInteger, nullable=True)
    # RNG state snapshots, one per sub-stream. Persisted so that a cold
    # reload resumes the exact pseudo-random trajectory — otherwise a
    # restarted sim re-seeds from master and tick N post-reload diverges
    # from tick N in the original continuous run (§9.11 contract extended
    # across process boundaries). `random.Random.getstate()` returns a
    # tuple of (version, 625-int tuple, gauss_next|None); we convert the
    # inner tuple to a list for JSONB round-tripping.
    rng_spawn_state = db.Column(JSONB, nullable=True)
    rng_tick_state = db.Column(JSONB, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=db.func.now(),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=db.func.now(),
    )

    __table_args__ = (
        db.Index(
            'uq_simulation_state_singleton',
            db.text('(true)'),
            unique=True,
        ),
    )
