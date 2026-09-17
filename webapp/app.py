"""KubeDeck Web application entry point.

The implementation lives in :mod:`webapp.server` so the desktop KubeDeck
process can import the FastAPI app without creating a second SSH connection.
"""

from .server import app, configure_runtime, get_server_url, start_server, stop_server

__all__ = ["app", "configure_runtime", "get_server_url", "start_server", "stop_server"]
