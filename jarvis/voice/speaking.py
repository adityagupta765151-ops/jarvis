"""Speech out.

Two engines. Edge TTS uses Microsoft's neural voices, which
sound like a person and include Indian English and Hindi; it needs a
network connection. pyttsx3 uses whatever Windows has locally, which is
robotic but always there. JARVIS prefers the neural one and falls back
without saying anything when it can't reach it.
"""
from __future__ import annotations

import asyncio
import os
import re
import tempfile
import threading
from pathlib import Path

from ..app.config import VOICE_RATE, log

# pyttsx3 needs a sound card, which a test run doesn't have. Importing
# without it is fine; only speaking aloud needs it.
try:
    import pyttsx3
except Exception:  # noqa: BLE001
    pyttsx3 = None


# Microsoft's neural voices. Indian English first, since that is who is
# usually talking to it. Full list: edge-tts --list-voices
NEURAL_VOICE = os.getenv("JARVIS_VOICE", "en-IN-PrabhatNeural")
NEURAL_RATE = os.getenv("JARVIS_VOICE_SPEED", "+8%")
NEURAL_PITCH = os.getenv("JARVIS_VOICE_PITCH", "+0Hz")
USE_NEURAL = os.getenv("JARVIS_NEURAL_VOICE", "true").lower() != "false"

SUGGESTED = {
    "en-IN-PrabhatNeural": "Indian English, male",
    "en-IN-NeerjaNeural": "Indian English, female",
    "hi-IN-MadhurNeural": "Hindi, male",
    "hi-IN-SwaraNeural": "Hindi, female",
    "en-GB-RyanNeural": "British English, male",
    "en-US-GuyNeural": "American English, male",
    "en-US-AriaNeural": "American English, female",
}

_tts_lock = threading.Lock()
_stop_flag = threading.Event()
_engine = None
_player = None
_neural_broken = False      # set once, so a missing package isn't retried per sentence


def _spoken(text: str) -> str:
    """Strip what should never be read out loud."""
    text = re.sub(r"```.*?```", " The code is in the file. ", text, flags=re.S)
    text = re.sub(r"https?://\S+", " the link ", text)
    text = re.sub(r"[*_#`>|]", "", text)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------- neural

def _synthesise(text: str, path: Path) -> bool:
    try:
        import edge_tts
    except ImportError:
        return False

    async def run():
        speech = edge_tts.Communicate(text, NEURAL_VOICE,
                                      rate=NEURAL_RATE, pitch=NEURAL_PITCH)
        await speech.save(str(path))

    try:
        asyncio.run(run())
        return path.exists() and path.stat().st_size > 800
    except Exception as e:  # noqa: BLE001
        log(f"edge-tts failed: {e}")
        return False


def _play(path: Path) -> bool:
    """Play an mp3, trying whichever player is installed."""
    global _player
    try:
        from playsound3 import playsound
        _player = playsound(str(path), block=False)
        while _player.is_alive():
            if _stop_flag.is_set():
                _player.stop()
                break
            _stop_flag.wait(0.05)
        _player = None
        return True
    except ImportError:
        pass
    except Exception as e:  # noqa: BLE001
        log(f"playsound3 failed: {e}")

    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if _stop_flag.is_set():
                pygame.mixer.music.stop()
                break
            _stop_flag.wait(0.05)
        pygame.mixer.music.unload()
        return True
    except ImportError:
        return False
    except Exception as e:  # noqa: BLE001
        log(f"pygame playback failed: {e}")
        return False


def _speak_neural(text: str) -> bool:
    global _neural_broken
    if _neural_broken or not USE_NEURAL:
        return False

    path = Path(tempfile.gettempdir()) / f"jarvis-speech-{os.getpid()}.mp3"
    if not _synthesise(text, path):
        _neural_broken = True
        log("falling back to the local voice for the rest of this session")
        return False
    try:
        return _play(path)
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------- local

def _best_local_voice(engine) -> str | None:
    """Windows 11 ships far better voices than the old default, but only if
    they have been added. Pick the best one present."""
    try:
        voices = engine.getProperty("voices")
    except Exception:  # noqa: BLE001
        return None

    def rank(voice) -> int:
        name = (getattr(voice, "name", "") or "").lower()
        if "natural" in name:
            return 0                      # the neural Windows voices
        if any(n in name for n in ("aria", "guy", "jenny", "ryan", "sonia")):
            return 1
        if "heera" in name or "ravi" in name:
            return 2                      # the Indian English pair
        return 3

    best = sorted(voices, key=rank)
    return best[0].id if best else None


def _speak_local(text: str) -> None:
    global _engine
    if pyttsx3 is None:
        log("no speech engine available; staying silent")
        return
    try:
        # A fresh engine per call keeps pyttsx3 from hanging on a second
        # runAndWait in a background thread.
        _engine = pyttsx3.init()
        chosen = _best_local_voice(_engine)
        if chosen:
            _engine.setProperty("voice", chosen)
        _engine.setProperty("rate", VOICE_RATE)
        _engine.say(text)
        _engine.runAndWait()
        _engine.stop()
    except Exception as e:  # noqa: BLE001
        log(f"tts failed: {e}")
    finally:
        _engine = None


# ---------------------------------------------------------------- public

def speak(text: str) -> None:
    text = _spoken(text)
    if not text:
        return
    _stop_flag.clear()
    with _tts_lock:
        if not _speak_neural(text[:900]):
            _speak_local(text[:700])


def stop_speaking() -> None:
    """Cut the current sentence short, whichever engine is talking."""
    _stop_flag.set()
    try:
        if _engine:
            _engine.stop()
    except Exception as e:  # noqa: BLE001
        log(f"tts stop failed: {e}")


def voice_report() -> str:
    """Which engine is actually being used, and what else is available."""
    lines = []
    try:
        import edge_tts  # noqa: F401
        lines.append(f"Neural voice: {NEURAL_VOICE} at {NEURAL_RATE}"
                     + (" (unavailable this session, using the local voice)"
                        if _neural_broken else ""))
    except ImportError:
        lines.append("Neural voice: not installed. Run: pip install edge-tts playsound3")

    if pyttsx3 is None:
        lines.append("Local voices: pyttsx3 isn't installed on this machine")
    else:
        try:
            engine = pyttsx3.init()
            names = [getattr(v, "name", "?") for v in engine.getProperty("voices")]
            engine.stop()
            lines.append("Local voices installed: " + (", ".join(names[:6]) or "none"))
        except Exception:  # noqa: BLE001
            lines.append("Local voices: couldn't read them")

    lines.append("Other neural voices you can set in .env as JARVIS_VOICE:")
    for name, description in SUGGESTED.items():
        lines.append(f"  {name:<24} {description}")
    return "\n".join(lines)
