"""JARVIS with the web interface.

The window is a real browser view, so the panel can be styled properly.
Python and the page talk through a small API: the page asks every 150 ms
what changed, which behaves the same on every pywebview version and keeps
all UI work on the UI thread.

If pywebview won't install, launcher.py still runs the plain window.
"""
from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

try:
    import webview
except ImportError:
    raise SystemExit(
        "The web interface needs pywebview. In the JARVIS folder run:\n"
        "    pip install pywebview\n"
        "Or run the plain window instead:  python launcher.py"
    )

from jarvis import tools
from jarvis.app import stats
from jarvis.app.config import API_KEY
from jarvis.app.config import log
from jarvis.app.assistant import Jarvis

UI = Path(__file__).resolve().parent / "ui" / "index.html"

# core.py's wording -> the page's state names
STATE_NAMES = {
    "offline": "offline",
    "calibrating": "calibrating",
    "listening": "listening",
    "waiting for command": "waiting",
    "thinking": "thinking",
    "executing": "executing",
    "speaking": "speaking",
}


class Api:
    """Everything the page is allowed to ask Python to do."""

    def __init__(self) -> None:
        self.lines: queue.Queue = queue.Queue()
        self.status = "offline"
        self.online = False
        self._stats_due = 0.0
        self._stats: dict | None = None

        self._ask: dict | None = None
        self._answers: dict[int, bool] = {}
        self._events: dict[int, threading.Event] = {}
        self._next_id = 0

        self.jarvis = Jarvis(log_fn=self.lines.put, status_fn=self._on_status)
        tools.set_confirm(self.confirm)

        if not API_KEY:
            self.lines.put("No GEMINI_API_KEY found. Add it to the .env file, then restart.")

    # -------------------------------------------------- from JARVIS

    def _on_status(self, status: str) -> None:
        self.status = STATE_NAMES.get(status, "listening")
        self.online = status != "offline"

    def confirm(self, message: str) -> bool:
        """Ask in the page and wait. Called from a worker thread."""
        self._next_id += 1
        ask_id = self._next_id
        event = threading.Event()
        self._events[ask_id] = event
        self._ask = {"id": ask_id, "message": message}

        if not event.wait(timeout=300):      # nobody answered; assume no
            self._ask = None
            return False
        return self._answers.pop(ask_id, False)

    # -------------------------------------------------- from the page

    def poll(self) -> dict:
        lines = []
        while not self.lines.empty() and len(lines) < 40:
            lines.append(self.lines.get())

        payload: dict = {"status": self.status, "lines": lines}

        # Readings are gathered twice a second, not on every poll, so the
        # panel stays live without the panel itself costing anything.
        now = time.monotonic()
        if now >= self._stats_due:
            self._stats_due = now + 0.5
            try:
                self._stats = stats.snapshot(self.jarvis, self.jarvis.muted)
            except Exception as e:  # noqa: BLE001
                log(f"stats failed: {e}")
        if self._stats:
            payload["stats"] = self._stats

        if self._ask:
            payload["ask"] = self._ask
            self._ask = None
        return payload

    def confirm_reply(self, ask_id: int, ok: bool) -> None:
        self._answers[ask_id] = bool(ok)
        event = self._events.pop(ask_id, None)
        if event:
            event.set()

    def toggle(self) -> None:
        if self.online:
            self.jarvis.stop()
        else:
            self.online = True
            self.jarvis.start()

    def send(self, text: str) -> None:
        text = (text or "").strip()
        if text:
            threading.Thread(target=self.jarvis.handle, args=(text,), daemon=True).start()

    def control(self, action: str) -> str:
        if action == "stop":
            self.jarvis.interrupt()
            return ""
        if action == "mute":
            self.jarvis.muted = not self.jarvis.muted
            return "Unmute voice" if self.jarvis.muted else "Mute voice"
        if action == "browser":
            def job():
                from jarvis.tools import browser
                self.lines.put(browser.close_browser())
            threading.Thread(target=job, daemon=True).start()
            return ""
        return ""


def main() -> None:
    api = Api()
    window = webview.create_window(
        "JARVIS",
        str(UI),
        js_api=api,
        width=1280,
        height=800,
        min_size=(1040, 660),
        background_color="#05070d",
    )

    def shutdown():
        api.jarvis.stop()
        try:
            from jarvis.tools import browser
            browser.close_browser()
        except Exception:  # noqa: BLE001
            pass

    window.events.closing += shutdown
    webview.start()


if __name__ == "__main__":
    main()
