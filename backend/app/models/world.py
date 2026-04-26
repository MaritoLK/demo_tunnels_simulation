from app import db


class WorldTile(db.Model):
    __tablename__ = 'world_tiles'

    id = db.Column(db.Integer, primary_key=True)
    x = db.Column(db.Integer, nullable=False)
    y = db.Column(db.Integer, nullable=False)
    terrain = db.Column(db.String(20), nullable=False)
    resource_type = db.Column(db.String(20), nullable=True)
    resource_amount = db.Column(db.Float, default=0.0, server_default='0.0')

    crop_state = db.Column(
        db.String(10), nullable=False,
        default='none', server_default='none',
    )
    crop_growth_ticks = db.Column(
        db.Integer, nullable=False,
        default=0, server_default='0',
    )
    crop_colony_id = db.Column(
        db.Integer,
        db.ForeignKey('colonies.id', ondelete='SET NULL'),
        nullable=True,
    )

    __table_args__ = (
        db.UniqueConstraint('x', 'y', name='uq_world_tiles_xy'),
        db.Index(
            'idx_tiles_resource',
            'resource_type',
            postgresql_where=db.text('resource_type IS NOT NULL'),
        ),
        db.Index(
            'idx_tiles_crop_state',
            'crop_state',
            postgresql_where=db.text("crop_state != 'none'"),
        ),
    )
