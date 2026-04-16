from app import db


class Colony(db.Model):
    __tablename__ = 'colonies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(7), nullable=False)     # '#rrggbb'
    camp_x = db.Column(db.Integer, nullable=False)
    camp_y = db.Column(db.Integer, nullable=False)
    food_stock = db.Column(
        db.Integer, nullable=False, default=0, server_default='0',
    )
