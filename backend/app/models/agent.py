from datetime import datetime, timezone                                                                                                                                                                            
from app import db                                                                                                                                                                                                 
                                                                                                                                                                                                                     
                  
class Agent(db.Model):
    __tablename__ = 'agents'
                                                                                                                                                                                                                    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)                                                                                                                                                                
    x = db.Column(db.Integer, nullable=False)
    y = db.Column(db.Integer, nullable=False)
    state = db.Column(db.String(20), nullable=False, default='idle')                                                                                                                                               
    hunger = db.Column(db.Float, nullable=False, default=100.0)
    energy = db.Column(db.Float, nullable=False, default=100.0)                                                                                                                                                    
    social = db.Column(db.Float, nullable=False, default=100.0)                                                                                                                                                    
    health = db.Column(db.Float, nullable=False, default=100.0)
    age = db.Column(db.Integer, nullable=False, default=0)                                                                                                                                                         
    alive = db.Column(db.Boolean, nullable=False, default=True)                                                                                                                                                    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))