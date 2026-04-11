from flask import Flask
from app import db
import os

def create_app():                                                                                                                                
    app = Flask(__name__)

    @app.route("/api/health")                                                                                                                        
    def health():            
        return {"status": "ok"}
    
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")  
    db.init_app(app)
    return app
    

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000)