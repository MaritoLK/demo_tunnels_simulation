from app import db                                                                                                                               
from datetime import datetime
                                                                                                                                                   
class SimulationState(db.Model):
    __tablename__ = 'simulation_state'
                                    
    id = db.Column(db.Integer, primary_key=True)
    current_tick = db.Column(db.Integer, nullable=False, default=0)                                                                              
    running = db.Column(db.Boolean, nullable=False, default=False) 
    speed = db.Column(db.Float, nullable=False, default=1.0)                                                                                     
    world_width = db.Column(db.Integer, nullable=False)     
    world_height = db.Column(db.Integer, nullable=False)                                                                                         
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)