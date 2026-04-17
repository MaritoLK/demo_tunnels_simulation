from sqlalchemy.dialects.postgresql import JSONB

from app import db


class GameStateRow(db.Model):
    """Singleton row holding the canonical game-state scalars.

    Only one row may ever exist (enforced via CHECK `id = 1`). Seeded by
    `app.services.game_service.new_game()`, never by migration.
    """

    __tablename__ = 'game_state'

    id = db.Column(db.Integer, primary_key=True)  # enforced singleton via CHECK
    tick = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    year = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    active_layer = db.Column(
        db.String(16), nullable=False, default='life_sim', server_default='life_sim',
    )
    alignment_axes_json = db.Column(
        JSONB, nullable=False, default=dict, server_default=db.text("'{}'::jsonb"),
    )

    __table_args__ = (
        db.CheckConstraint('id = 1', name='game_state_singleton'),
    )
