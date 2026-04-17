from sqlalchemy.dialects.postgresql import JSONB

from app import db


class Policy(db.Model):
    """A strategic-layer policy (tax / levy / law / trade in MVP).

    Effects live in the `effects_json` blob — no separate modifier table
    in MVP (spec §2 persistence). `active_until_tick=NULL` means the
    policy is open-ended; a future tick bounds the effect window.
    """

    __tablename__ = 'policies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), nullable=False)
    effects_json = db.Column(
        JSONB, nullable=False, default=dict, server_default=db.text("'{}'::jsonb"),
    )
    active_until_tick = db.Column(db.Integer, nullable=True)
