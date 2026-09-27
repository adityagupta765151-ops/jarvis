"""Who gets asked before something irreversible happens.

This lives on its own so every tool module can ask for confirmation
without importing the registry that imports them back.
"""
from __future__ import annotations

from typing import Callable


def _ask_on_the_terminal(message: str) -> bool:
    return input(f"{message} [y/N] ").strip().lower() == "y"


confirm_fn: Callable[[str], bool] = _ask_on_the_terminal


def set_confirm(fn: Callable[[str], bool]) -> None:
    """The launcher swaps this for a dialog in the panel."""
    global confirm_fn
    confirm_fn = fn


def confirm(message: str) -> bool:
    """Ask. Always read through this name, never by importing confirm_fn
    directly, or a module captures whatever was installed at import time."""
    return confirm_fn(message)


# Tools that must never run without a yes. Applying to a job is not on this
# list because it is not automated at all: JARVIS fills a form and stops.
NEEDS_CONFIRMATION = {
    "delete_path",
    "run_command",
    "send_whatsapp_message",
    "wa_send_web",
    "click_text",
}
