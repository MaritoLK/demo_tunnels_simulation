"""Service-layer exceptions. Routes translate these to HTTP status codes.

Kept deliberately thin: a class per distinct failure shape the route layer
needs to discriminate. Resist the urge to attach payloads or error codes —
the message carries the human-readable part, and any structured context
belongs in the raising code, not on the exception type.
"""


class SimulationError(Exception):
    """Base for service-layer simulation failures."""


class SimulationNotFoundError(SimulationError):
    """No simulation exists — neither in memory nor in the DB.

    Routes map this to 404. Raised by get_current_simulation / step when
    there's nothing to operate on.
    """


class SimulationStateError(SimulationError):
    """Simulation exists but is in a state that forbids the requested op.

    Routes map this to 409 Conflict. Placeholder for future checks like
    'can't step a sim that's currently marked running by a background
    worker'. Not raised anywhere yet.
    """
