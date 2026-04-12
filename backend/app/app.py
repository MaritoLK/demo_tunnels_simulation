import os

from flask import Flask
from flask_migrate import Migrate

from app import db
from app import models  # noqa: F401 — side-effect import: registers models with db.metadata

migrate = Migrate()


def create_app():
    app = Flask(__name__)

    @app.route("/api/health")
    def health():
        return {"status": "ok"}

    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")

    db.init_app(app)
    migrate.init_app(app, db)
    return app
    

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000)