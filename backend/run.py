"""
AutoDesk - Development entry point
==================================

Run the API on http://localhost:5000::

    python run.py
    # or
    flask --app run.py run

The Vite dev server (http://localhost:5173) proxies ``/api/*`` here, so the
frontend only ever talks to relative ``/api/...`` URLs.
"""

from __future__ import annotations

import os
import sys

# Allow `python run.py` from anywhere by putting backend/ on sys.path.
_BACKEND_ROOT = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app import create_app  # noqa: E402

app = create_app()


def main() -> None:
    """Start the development server with the threaded mode the SRS requires."""
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = bool(app.config.get("DEBUG"))

    print("=" * 68)
    print("  AutoDesk API")
    print(f"  Listening on   http://localhost:{port}")
    print(f"  Health check   http://localhost:{port}/api/health")
    print(f"  Frontend       http://localhost:5173")
    print(f"  Debug mode     {debug}")
    print("  Ctrl+C to stop")
    print("=" * 68)

    app.run(host=host, port=port, debug=debug, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
