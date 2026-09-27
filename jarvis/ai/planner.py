"""Breaking a big request into steps, then working through them.

Only complex requests come here. A one-line job goes straight to the
brain, because planning costs an extra model call and would only slow it
down. While a plan runs, its steps and their state are readable from
`current()`, which is what the panel shows.
"""
from __future__ import annotations

import re
import threading

from ..app.config import log
from .prompts import PLAN, STEP
from .provider import ask_text

MAX_STEPS = 8

# Phrasings that suggest more than one action. Deliberately narrow: a
# request that slips through just goes to the brain as before.
COMPLEX = re.compile(
    r"\b(and then|then |after that|first .* then)\b"
    r"|\b(create|make|build|set ?up|scaffold|generate)\b.*\b(project|app|website|api|server|component)\b"
    r"|\brun (my|the) project\b"
    r"|\b(install|clone)\b.*\b(and|then)\b"
    r"|\bfix\b.*\b(all|every|errors)\b", re.I)

FAILED = re.compile(r"^FAILED:|(\bI )?(couldn't|could not|failed to|unable to)\b", re.I)

_lock = threading.Lock()
_current: dict | None = None
_cancel = threading.Event()


def current() -> dict | None:
    """What the panel shows: the goal, the steps and where we are."""
    return _current


def cancel() -> None:
    _cancel.set()


def should_plan(command: str) -> bool:
    """Worth the extra call? Only for requests that clearly have parts."""
    text = command.strip()
    if len(text.split()) < 5:
        return False
    return bool(COMPLEX.search(text))


def _parse(raw: str) -> list[str]:
    steps = []
    for line in raw.splitlines():
        match = re.match(r"\s*(\d+)[.)]\s+(.{3,})", line)
        if match:
            steps.append(match.group(2).strip().rstrip("."))
    return steps[:MAX_STEPS]


def run(command: str, brain, say, status) -> str:
    """Plan the request, then carry it out step by step.

    `say` puts a line in the activity log; `status` sets the panel state.
    Returns the sentence to speak at the end.
    """
    global _current

    if not _lock.acquire(blocking=False):
        return "I'm already working through a plan. Say stop to cancel it."

    _cancel.clear()
    try:
        status("thinking")
        try:
            raw = ask_text(PLAN.format(goal=command, max=MAX_STEPS))
        except RuntimeError as e:
            return str(e)

        if raw.strip().upper().startswith("SIMPLE"):
            return brain.ask(command)

        steps = _parse(raw)
        if len(steps) < 2:
            return brain.ask(command)

        _current = {"goal": command, "steps": steps, "at": 0, "done": []}
        say(f"Plan: {len(steps)} steps")
        for i, step in enumerate(steps, 1):
            say(f"   {i}. {step}")

        plan_text = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
        results: list[str] = []

        for i, step in enumerate(steps, 1):
            if _cancel.is_set():
                _current["at"] = 0
                return f"Stopped after step {i - 1} of {len(steps)}."

            _current["at"] = i
            status("executing")
            say(f"[{i}/{len(steps)}] {step}")

            try:
                reply = brain.ask(STEP.format(goal=command, plan=plan_text, n=i))
            except Exception as e:  # noqa: BLE001
                log(f"plan step {i} crashed: {e}")
                reply = f"FAILED: {e}"

            clean = re.sub(r"^FAILED:\s*", "", reply).strip()
            failed = bool(FAILED.match(reply))
            _current["done"].append({"ok": not failed, "text": step})
            results.append(clean)
            say(f"      {'could not: ' if failed else ''}{clean}")

            if failed:
                return (f"I got to step {i} of {len(steps)} and stopped: {clean} "
                        f"Tell me how to get past it and I'll carry on.")

        return f"Done, all {len(steps)} steps. {results[-1]}"
    finally:
        _current = None
        _lock.release()
