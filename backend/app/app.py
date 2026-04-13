"""Application factory.

Responsibilities kept here (and nowhere else):
  * Extension wiring: SQLAlchemy, Migrate, CORS.
  * Blueprint registration — url_prefix lives here so `/api/v1` → `/api/v2`
    is a one-line change (see STUDY_NOTES §9.21).
  * App-level errorhandlers that translate service-layer exceptions to
    HTTP status codes. Service code stays driver-agnostic.
  * Health check — deliberately outside the versioned blueprint so
    liveness probes don't break on API version bumps.
"""
import logging
import os
import traceback

from flask import Flask
from flask_cors import CORS
from flask_migrate import Migrate

from app import db
from app import models  # noqa: F401 — side-effect import: registers models with db.metadata
from app.routes.simulation import bp as simulation_bp
from app.services import tick_loop
from app.services.exceptions import SimulationNotFoundError, SimulationStateError


migrate = Migrate()
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")

    db.init_app(app)
    migrate.init_app(app, db)

    # Dev ergonomics: React (Vite) on :3000 talking to Flask on :5000 is
    # a cross-origin call and preflights fail without this. Scoped to
    # /api/* so the health check and any future static routes stay open.
    cors_origins = os.environ.get(
        "CORS_ORIGINS", "http://localhost:3000"
    ).split(",")
    CORS(app, resources={r"/api/*": {"origins": cors_origins}})

    @app.route("/api/health")
    def health():
        return {"status": "ok"}

    app.register_blueprint(simulation_bp, url_prefix="/api/v1")

    _register_error_handlers(app)

    # Start the background tick loop unless explicitly disabled (tests set
    # DISABLE_TICK_LOOP=1 so the loop doesn't mutate DB state while the
    # test client is driving it via POST /step). See §9.27.
    if not os.environ.get("DISABLE_TICK_LOOP"):
        tick_loop.start(app)

    return app


def _register_error_handlers(app):
    """Domain → HTTP translation. Lives here so service code stays pure.

    Registered at app level (not on the blueprint) so the same error
    classes translate identically whether raised from a route, a CLI
    command, or a future admin blueprint — see STUDY_NOTES §9.21.
    """

    @app.errorhandler(SimulationNotFoundError)
    def _not_found(e):
        return {"error": str(e) or "simulation not found"}, 404

    @app.errorhandler(SimulationStateError)
    def _conflict(e):
        return {"error": str(e) or "simulation state conflict"}, 409

    @app.errorhandler(ValueError)
    def _bad_value(e):
        # Engine/service raise ValueError for invariant violations (world
        # too big, ticks out of range, etc). Route-layer bounds mostly
        # catch these first, but if one slips through it's still user-
        # correctable input, not a 500.
        return {"error": str(e)}, 400

    @app.errorhandler(400)
    def _bad_request(e):
        # abort(400, description={...}) from the route layer passes a
        # dict through e.description; plain abort(400) passes a string.
        description = getattr(e, "description", None)
        if isinstance(description, dict):
            return description, 400
        return {"error": str(description) if description else "bad request"}, 400

    @app.errorhandler(404)
    def _http_not_found(e):
        # Distinct from SimulationNotFoundError: this is "no such route"
        # (wrong URL), not "no such simulation" (no sim persisted).
        return {"error": "not found"}, 404

    @app.errorhandler(Exception)
    def _internal(e):
        # Catch-all so the default Werkzeug traceback never leaks into
        # the response body. Traceback still goes to server logs.
        logger.error("unhandled exception", exc_info=e)
        traceback.print_exc()
        return {"error": "internal server error"}, 500


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000)
