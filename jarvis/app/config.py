"""One place for paths, settings and logging. Everything else imports this."""
from __future__ import annotations

import datetime
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

WORKSPACE = Path(
    os.getenv("JARVIS_WORKSPACE", str(Path.home() / "JarvisWorkspace"))
).expanduser().resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)

MEMORY_DIR = BASE_DIR / "memory"
MEMORY_DIR.mkdir(exist_ok=True)
LOG_FILE = BASE_DIR / "jarvis.log"

WAKE_WORDS = [
    w.strip().lower()
    for w in os.getenv("JARVIS_WAKE", "hey jarvis,jarvis,jervis,javis").split(",")
    if w.strip()
]
LANG = os.getenv("JARVIS_LANG", "en-IN")
VOICE_RATE = int(os.getenv("JARVIS_VOICE_RATE", "185"))
MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
API_KEY = os.getenv("GEMINI_API_KEY")

# Browser automation
BROWSER_HEADLESS = os.getenv("JARVIS_BROWSER_HEADLESS", "false").lower() == "true"
BROWSER_PROFILE = BASE_DIR / "browser_profile"


def log(message: str) -> None:
    """Technical detail goes to the log file, not to the user."""
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    try:
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"[{stamp}] {message}\n")
    except OSError:
        pass
