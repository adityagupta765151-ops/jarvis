"""The local dashboard at http://localhost:3000/jobs

Served by Python's own http.server on a background thread, so there is no
Node, no npm and no build step. The page asks /api/state for everything
and redraws; JARVIS never pushes to it.
"""
from __future__ import annotations

import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..app.config import BASE_DIR, log
from . import store
from .resume import load_profile

UI_DIR = BASE_DIR / "ui" / "jobs"
PORT = 3000

_server: ThreadingHTTPServer | None = None


def state() -> dict:
    """Everything the page shows, read fresh from the database."""
    counts = store.counts()
    jobs = store.top_jobs(limit=60)
    profile = load_profile()
    person = profile.get("candidate", {})

    return {
        "counts": counts,
        "jobs": jobs,
        "applications": store.applications(limit=40),
        "audit": store.audit_trail(limit=60),
        "missing_skills": store.missing_skill_counts(12),
        "resume": {
            "name": person.get("name", ""),
            "file": profile.get("source_file", ""),
            "skills": person.get("skills", []),
            "degree": person.get("degree", ""),
            "graduation_year": person.get("graduation_year", ""),
            "location": person.get("location", ""),
            "projects": person.get("projects", []),
            "roles": profile.get("preferences", {}).get("roles", []),
        },
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/api/state"):
            return self._json(state())
        if self.path in ("/", "/jobs", "/jobs/"):
            self.path = "/index.html"
        return super().do_GET()

    def _json(self, payload: dict) -> None:
        body = json.dumps(payload, default=str).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        """Keep request noise out of the terminal; it goes to jarvis.log."""
        log("dashboard: " + (fmt % args))


def start() -> str:
    """Start the dashboard if it isn't already running."""
    global _server
    if _server is not None:
        return f"The dashboard is already at http://localhost:{PORT}/jobs"

    if not (UI_DIR / "index.html").exists():
        return f"The dashboard files are missing from {UI_DIR}."

    try:
        _server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        log(f"dashboard bind failed: {e}")
        return (f"Port {PORT} is already in use by something else. "
                f"Close it, or the dashboard can't start.")

    threading.Thread(target=_server.serve_forever, daemon=True).start()
    log(f"dashboard listening on {PORT}")
    return f"Dashboard running at http://localhost:{PORT}/jobs"


def stop() -> str:
    global _server
    if _server is None:
        return "The dashboard isn't running."
    _server.shutdown()
    _server.server_close()
    _server = None
    return "Dashboard stopped."


def open_dashboard() -> str:
    """Start it if needed, then show it."""
    import webbrowser

    message = start()
    if "running" in message or "already" in message:
        webbrowser.open(f"http://localhost:{PORT}/jobs")
    return message
