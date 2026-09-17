"""KubeDeck Web application entry point.

The implementation lives in :mod:`webapp.server` so the same FastAPI app can
be imported by the desktop KubeDeck process without creating a second SSH
connection.
"""

from .server import app, configure_runtime, start_server, stop_server

__all__ = ["app", "configure_runtime", "start_server", "stop_server"]
