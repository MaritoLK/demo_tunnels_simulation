from sqlalchemy.dialects.postgresql import JSONB

from app import db


class NPC(db.Model):
    """Named NPC registry row.

    Tiers follow spec §2 (T1 hero/spouse/council ~25, T2 recurring ~100,
    T3 flavor ~500, T4 generic unbounded/scalar-only — not stored here).
    `stats_json` is a dict (competence/loyalty/ambition/specialty/…);
    `memory_json` is a list (ring buffer for T2, full log for T1).
    """

    __tablename__ = 'npcs'

    id = db.Column(db.Integer, primary_key=True)
    tier = db.Column(db.SmallInteger, nullable=False)
    name = db.Column(db.String(64), nullable=False)
    stats_json = db.Column(
        JSONB, nullable=False, default=dict, server_default=db.text("'{}'::jsonb"),
    )
    memory_json = db.Column(
        JSONB, nullable=False, default=list, server_default=db.text("'[]'::jsonb"),
    )
    status = db.Column(
        db.String(16), nullable=False, default='alive', server_default='alive',
    )

    __table_args__ = (
        db.Index('idx_npcs_tier_status', 'tier', 'status'),
    )
