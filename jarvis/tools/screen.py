"""Looking at the screen, only when you ask."""
from __future__ import annotations

import datetime
import io

from ..app.config import MEMORY_DIR, log
from ..ai.provider import ask_about_image


def _grab() -> bytes | None:
    try:
        from PIL import ImageGrab
        image = ImageGrab.grab()
    except Exception:  # noqa: BLE001
        try:
            import pyautogui
            image = pyautogui.screenshot()
        except Exception as e:  # noqa: BLE001
            log(f"screenshot failed: {e}")
            return None
    image.thumbnail((1600, 1600))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def take_screenshot() -> str:
    """Save a screenshot to the memory folder."""
    data = _grab()
    if not data:
        return "I couldn't capture the screen. Install pillow with pip install pillow."
    path = MEMORY_DIR / datetime.datetime.now().strftime("screen-%H%M%S.png")
    path.write_bytes(data)
    return f"Screenshot saved to {path}."


def describe_screen(question: str = "What is on this screen? If there is an error, explain it.") -> str:
    """Capture the screen and have the model read it."""
    data = _grab()
    if not data:
        return "I couldn't capture the screen. Install pillow with pip install pillow."
    try:
        return ask_about_image(data, question)
    except Exception as e:  # noqa: BLE001
        log(f"describe_screen failed: {e}")
        return str(e) or "Something went wrong while reading the screen."
