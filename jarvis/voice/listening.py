"""Speech in.

The microphone, the room calibration and the recogniser. Tuned from .env
because a quiet bedroom and a room with a fan need different settings.
"""
from __future__ import annotations

import os

from ..app.config import LANG, log

# Blank MIC_INDEX means the system default; blank sensitivity means
# calibrate against the room instead of holding a fixed floor.
MIC_INDEX = os.getenv("JARVIS_MIC")
PAUSE = float(os.getenv("JARVIS_PAUSE", "1.0"))
ENERGY = os.getenv("JARVIS_MIC_SENSITIVITY")

try:
    import speech_recognition as sr
except Exception:  # noqa: BLE001
    sr = None

class Listener:
    def __init__(self, device_index: int | None = None) -> None:
        if sr is None:
            raise RuntimeError("SpeechRecognition isn't installed, so voice input is off.")

        if device_index is None and MIC_INDEX and MIC_INDEX.strip().isdigit():
            device_index = int(MIC_INDEX)

        self.recognizer = sr.Recognizer()
        # A pause longer than this ends the phrase. Too short and it cuts
        # you off mid-sentence; too long and every command feels slow.
        self.recognizer.pause_threshold = PAUSE
        self.recognizer.non_speaking_duration = min(0.5, PAUSE / 2)

        if ENERGY and ENERGY.strip():
            self.recognizer.energy_threshold = float(ENERGY)
            self.recognizer.dynamic_energy_threshold = False
        else:
            self.recognizer.dynamic_energy_threshold = True

        self.mic = sr.Microphone(device_index=device_index)
        self.device_index = device_index
        self.calibrate()

    def calibrate(self, seconds: float = 1.2) -> str:
        """Learn the room's background noise. Worth redoing when a fan goes
        on, or when it starts triggering on nothing."""
        if ENERGY and ENERGY.strip():
            return f"Using the fixed sensitivity you set: {self.recognizer.energy_threshold:.0f}"
        with self.mic as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=seconds)
        return (f"Calibrated. Background noise reads "
                f"{self.recognizer.energy_threshold:.0f}; I'll listen above that.")

    @staticmethod
    def devices() -> list[str]:
        if sr is None:
            return []
        try:
            return list(sr.Microphone.list_microphone_names())
        except Exception:  # noqa: BLE001
            return []

    def listen(self, timeout: float = 5, phrase_limit: float = 12) -> str | None:
        with self.mic as source:
            try:
                audio = self.recognizer.listen(source, timeout=timeout,
                                               phrase_time_limit=phrase_limit)
            except sr.WaitTimeoutError:
                return None
        try:
            return self.recognizer.recognize_google(audio, language=LANG).lower()
        except sr.UnknownValueError:
            return None                     # heard sound, made no words of it
        except sr.RequestError as e:
            raise ConnectionError(f"Speech service unreachable: {e}") from e


def microphones() -> str:
    """List the input devices, so a better one than the default can be picked."""
    names = Listener.devices()
    if not names:
        return "I can't see any microphones. Check Windows sound settings."
    lines = ["Microphones this machine reports:"]
    for i, name in enumerate(names):
        lines.append(f"  {i:>2}  {name}")
    lines.append("")
    lines.append("To use one, put its number in .env as JARVIS_MIC, then restart.")
    return "\n".join(lines)
