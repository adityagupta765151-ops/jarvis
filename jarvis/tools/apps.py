"""Launching and closing desktop applications, whatever the OS."""
from __future__ import annotations

import platform
import shutil
import subprocess

from ..app.config import log

SYSTEM = platform.system()

# What the user says -> what to actually launch, per OS.
APPS = {
    "chrome": {"Windows": "chrome", "Darwin": "Google Chrome", "Linux": "google-chrome"},
    "edge": {"Windows": "msedge", "Darwin": "Microsoft Edge", "Linux": "microsoft-edge"},
    "firefox": {"Windows": "firefox", "Darwin": "Firefox", "Linux": "firefox"},
    "vs code": {"Windows": "code", "Darwin": "Visual Studio Code", "Linux": "code"},
    "vscode": {"Windows": "code", "Darwin": "Visual Studio Code", "Linux": "code"},
    "whatsapp": {"Windows": "whatsapp", "Darwin": "WhatsApp", "Linux": "whatsapp"},
    "spotify": {"Windows": "spotify", "Darwin": "Spotify", "Linux": "spotify"},
    "notepad": {"Windows": "notepad", "Darwin": "TextEdit", "Linux": "gedit"},
    "calculator": {"Windows": "calc", "Darwin": "Calculator", "Linux": "gnome-calculator"},
    "explorer": {"Windows": "explorer", "Darwin": "Finder", "Linux": "nautilus"},
    "terminal": {"Windows": "wt", "Darwin": "Terminal", "Linux": "gnome-terminal"},
    "settings": {"Windows": "ms-settings:", "Darwin": "System Settings", "Linux": "gnome-control-center"},
}

# Processes to kill, by app name, on Windows.
PROCESSES = {
    "chrome": "chrome.exe",
    "edge": "msedge.exe",
    "firefox": "firefox.exe",
    "vs code": "Code.exe",
    "vscode": "Code.exe",
    "whatsapp": "WhatsApp.exe",
    "spotify": "Spotify.exe",
    "notepad": "notepad.exe",
}


def resolve(name: str) -> str | None:
    key = name.lower().strip()
    entry = APPS.get(key)
    return entry.get(SYSTEM) if entry else None


def open_app(name: str) -> str:
    """Open an application by its everyday name."""
    target = resolve(name) or name
    try:
        if SYSTEM == "Windows":
            subprocess.Popen(f'start "" "{target}"', shell=True)
        elif SYSTEM == "Darwin":
            subprocess.Popen(["open", "-a", target])
        else:
            if not shutil.which(target):
                return f"I couldn't open {name} because it doesn't seem to be installed."
            subprocess.Popen([target])
        return f"Opening {name}."
    except Exception as e:  # noqa: BLE001
        log(f"open_app({name}) failed: {e}")
        return f"I couldn't open {name}. It may not be installed."


def close_app(name: str) -> str:
    """Close an application."""
    key = name.lower().strip()
    try:
        if SYSTEM == "Windows":
            process = PROCESSES.get(key, f"{key}.exe")
            result = subprocess.run(
                ["taskkill", "/im", process, "/f"], capture_output=True, text=True
            )
            if result.returncode != 0:
                return f"{name} doesn't seem to be running."
        elif SYSTEM == "Darwin":
            subprocess.run(["osascript", "-e", f'quit app "{resolve(name) or name}"'])
        else:
            subprocess.run(["pkill", "-f", key])
        return f"Closed {name}."
    except Exception as e:  # noqa: BLE001
        log(f"close_app({name}) failed: {e}")
        return f"I couldn't close {name}."
