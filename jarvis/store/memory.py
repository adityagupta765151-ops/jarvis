"""Local memory: who you are, what you like, who your contacts are.

Plain JSON files under memory/ so you can read and edit them yourself.
Nothing secret goes in here.
"""
from __future__ import annotations

import json
from typing import Any

from ..app.config import MEMORY_DIR, log

PROFILE = MEMORY_DIR / "user_profile.json"
PREFERENCES = MEMORY_DIR / "preferences.json"
CONTACTS = MEMORY_DIR / "contacts.json"
HISTORY = MEMORY_DIR / "conversation_history.json"

DEFAULTS = {
    PROFILE: {"name": "", "language": "en-IN"},
    PREFERENCES: {"browser": "chrome", "editor": "code", "facts": {}},
    CONTACTS: {"example": "+911234567890"},
    HISTORY: [],
}


def _load(path) -> Any:
    if not path.exists():
        _save(path, DEFAULTS[path])
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log(f"memory read failed for {path.name}: {e}")
        return DEFAULTS[path]


def _save(path, data) -> None:
    try:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        log(f"memory write failed for {path.name}: {e}")


def profile() -> dict:
    return _load(PROFILE)


def preferences() -> dict:
    return _load(PREFERENCES)


def contacts() -> dict:
    return _load(CONTACTS)


def remember(key: str, value: str) -> str:
    prefs = preferences()
    prefs.setdefault("facts", {})[key.lower().strip()] = value
    _save(PREFERENCES, prefs)
    return f"Noted: {key} is {value}."


def forget(key: str) -> str:
    prefs = preferences()
    if prefs.get("facts", {}).pop(key.lower().strip(), None) is None:
        return f"I had nothing stored under {key}."
    _save(PREFERENCES, prefs)
    return f"Forgotten: {key}."


def recall(key: str | None = None) -> str:
    facts = preferences().get("facts", {})
    if not facts:
        return "I haven't stored any preferences yet."
    if key:
        return facts.get(key.lower().strip(), f"Nothing stored under {key}.")
    return "; ".join(f"{k}: {v}" for k, v in facts.items())


def add_contact(name: str, number: str) -> str:
    book = contacts()
    book[name.lower().strip()] = number.strip()
    _save(CONTACTS, book)
    return f"Saved {name} in your contacts."


def find_contact(name: str) -> str | None:
    book = contacts()
    key = name.lower().strip()
    if key in book:
        return book[key]
    for alias, number in book.items():
        if key in alias or alias in key:
            return number
    return None


def log_turn(user: str, assistant: str) -> None:
    history = _load(HISTORY)
    history.append({"user": user, "assistant": assistant})
    _save(HISTORY, history[-200:])
