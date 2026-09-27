"""The loop that ties it together.

voice -> wake word -> fast router -> (if needed) AI brain -> speech
"""
from __future__ import annotations

import json
import os
import re
import threading
import time

from . import stats
from ..ai import planner
from ..routing.router import fast_route
from ..store import memory
from ..tools import reminders
from ..voice import Listener, speak, stop_speaking, wake_position
from .config import log

# Showing every phrase it heard is the difference between "the mic is
# broken" and "it hears me but not my name".
SHOW_HEARD = os.getenv("JARVIS_SHOW_HEARD", "true").lower() != "false"

SLEEP_PHRASES = ("go to sleep", "stop listening", "so jao", "goodbye jarvis")
RESET_PHRASES = ("new conversation", "clear memory", "start fresh")
CALIBRATE_PHRASES = ("recalibrate mic", "calibrate mic", "recalibrate microphone",
                     "tune the mic", "mic calibrate")
STOP_PHRASES = ("stop", "cancel", "ruko", "chup")


class Jarvis:
    def __init__(self, log_fn=print, status_fn=lambda s: None) -> None:
        self.log = log_fn
        self.status = status_fn
        self.brain = None
        self.listener: Listener | None = None
        self.running = False
        self.muted = False
        self._busy = threading.Lock()
        reminders.set_speaker(self.say)

    # ------------------------------------------------------------ control

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._voice_loop, daemon=True).start()

    def stop(self) -> None:
        self.running = False
        stop_speaking()
        self.status("offline")

    def interrupt(self) -> None:
        """Esc: stop talking, and give up on any plan still running."""
        stop_speaking()
        planner.cancel()

    # ------------------------------------------------------------ voice loop

    def _voice_loop(self) -> None:
        try:
            if self.listener is None:
                self.status("calibrating")
                self.listener = Listener()
        except Exception as e:  # noqa: BLE001
            log(f"mic init failed: {e}")
            self.log("I couldn't reach your microphone, so voice is off. Typed commands still work.")
            self.stop()
            return

        self.say("JARVIS online.")
        self.status("listening")
        misses = 0

        while self.running:
            try:
                heard = self.listener.listen(timeout=5, phrase_limit=10)
            except ConnectionError:
                self.log("I can't reach the speech service. Check your internet.")
                time.sleep(5)
                continue
            if not self.running:
                continue
            if not heard:
                misses += 1
                # Long silence usually means the mic is on the wrong device
                # or the room got louder than it was at startup.
                if misses == 25:
                    self.log("I haven't made out anything in a while. Say "
                             "recalibrate mic, or list microphones to pick another.")
                continue
            misses = 0

            end = wake_position(heard)
            if end is None:
                if SHOW_HEARD:
                    self.log(f"   heard: {heard}")
                continue

            command = heard[end:].strip(" ,.!?")
            if not command:
                self.status("waiting for command")
                self.say("Yes?")
                command = self.listener.listen(timeout=7, phrase_limit=20) or ""

            if command:
                self.handle(command)
            if self.running:
                self.status("listening")

    # ------------------------------------------------------------ commands

    def handle(self, command: str) -> None:
        self.log(f"You: {command}")
        stats.note_command()
        low = command.lower().strip()

        if low in STOP_PHRASES:
            self.interrupt()
            self.log("JARVIS: Stopped.")
            return
        if any(p in low for p in SLEEP_PHRASES):
            self.say("Going offline.")
            self.stop()
            return
        if any(p in low for p in CALIBRATE_PHRASES):
            if self.listener is None:
                self.log("JARVIS: The mic isn't on yet. Click the core first.")
                return
            self.say("Stay quiet for a moment.")
            result = self.listener.calibrate(1.8)
            self.log(f"JARVIS: {result}")
            self.say("Done. Try me again.")
            return

        if re.fullmatch(r"(list |show )?(my )?(microphones|mics|mic list)\.?", low):
            from .voice import microphones
            self.log(microphones())
            return

        if any(p in low for p in RESET_PHRASES):
            if self.brain:
                self.brain.reset()
            self.say("Fresh start. What's next?")
            return

        with self._busy:
            self.status("executing")
            try:
                reply = fast_route(command)  # usually milliseconds, no model call
            except Exception as e:  # noqa: BLE001
                log(f"router failed: {e}")
                reply = None

            if reply is None:
                self.status("thinking")
                try:
                    if self.brain is None:
                        from .brain import Brain
                        self.brain = Brain()

                    if planner.should_plan(command):
                        # Several parts to this one: plan it, then work through.
                        reply = planner.run(command, self._planning_brain(),
                                            self.log, self.status)
                    else:
                        reply = self.brain.ask(command, on_action=self._show_action)
                except Exception as e:  # noqa: BLE001
                    log(f"brain failed: {e}")
                    reply = str(e) if str(e) else "Something went wrong on my side."

            self.status("listening" if self.running else "offline")

        self.log(f"JARVIS: {reply}")
        memory.log_turn(command, reply)
        self.say(reply)

    def _planning_brain(self):
        """The planner calls ask() without knowing about the activity log,
        so hand it a brain that already reports its tool calls."""
        brain = self.brain
        show = self._show_action

        class Reporting:
            def ask(self, text):
                return brain.ask(text, on_action=show)

        return Reporting()

    def _show_action(self, name: str, args: dict) -> None:
        preview = {k: (v[:60] + "..." if isinstance(v, str) and len(v) > 60 else v)
                   for k, v in args.items()}
        self.log(f"   > {name} {json.dumps(preview, ensure_ascii=False)}")

    def say(self, text: str) -> None:
        if self.muted:
            return
        self.status("speaking")
        speak(text)
        if self.running:
            self.status("listening")
