from app import db


class SaveMeta(db.Model):
    """Singleton save-metadata row.

    Only one row may ever exist (enforced via CHECK `id = 1`), mirroring
    GameStateRow. `seed` has NO default — callers MUST provide it
    explicitly so a bug that forgets the seed fails loudly instead of
    silently using a zero default.
    """

    __tablename__ = 'save_meta'

    id = db.Column(db.Integer, primary_key=True)
    schema_version = db.Column(
        db.Integer, nullable=False, default=1, server_default='1',
    )
    playtime_seconds = db.Column(
        db.Integer, nullable=False, default=0, server_default='0',
    )
    gen_number = db.Column(
        db.Integer, nullable=False, default=1, server_default='1',
    )
    seed = db.Column(db.BigInteger, nullable=False)

    __table_args__ = (
        db.CheckConstraint('id = 1', name='save_meta_singleton'),
    )
