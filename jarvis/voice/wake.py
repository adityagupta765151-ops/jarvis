"""Hearing its own name.

Speech recognition mangles a name it doesn't know, so an exact match on
its own loses a lot of real attempts. Anything close enough counts, while
ordinary words that merely rhyme do not.
"""
from __future__ import annotations

import difflib
import os
import re

from ..app.config import WAKE_WORDS

WAKE_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in WAKE_WORDS) + r")\b")
WAKE_STEMS = {w.split()[-1] for w in WAKE_WORDS}
FUZZY = float(os.getenv("JARVIS_WAKE_FUZZY", "0.72"))


def wake_position(heard: str) -> int | None:
    """Where the wake word ends in the heard phrase, or None if it isn't there."""
    match = WAKE_RE.search(heard)
    if match:
        return match.end()

    # Fall back to checking the opening words for something close.
    words = heard.split()
    for i, word in enumerate(words[:3]):
        if difflib.get_close_matches(word, WAKE_STEMS, n=1, cutoff=FUZZY):
            return len(" ".join(words[:i + 1]))
    return None
