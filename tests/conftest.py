"""Shared test setup.

The workspace has to be pointed at a temporary folder before anything
under jarvis/ is imported, because config.py reads it at import time and
creates it. Nothing here touches the real machine.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_sandbox = Path(tempfile.mkdtemp(prefix="jarvis-tests-"))
os.environ["JARVIS_WORKSPACE"] = str(_sandbox)
os.environ["GEMINI_API_KEY"] = "test-key-not-used"
os.environ["JARVIS_BROWSER_HEADLESS"] = "true"

import pytest  # noqa: E402

from jarvis import tools
from jarvis.store import memory  # noqa: E402


@pytest.fixture
def workspace() -> Path:
    return _sandbox


@pytest.fixture(autouse=True)
def clean_workspace():
    """Every test starts with an empty workspace and no stored memory."""
    for item in _sandbox.iterdir():
        if item.is_dir():
            __import__("shutil").rmtree(item)
        else:
            item.unlink()
    for path in (memory.PREFERENCES, memory.CONTACTS, memory.HISTORY, memory.PROFILE):
        if path.exists():
            path.unlink()

    # The job database and resume profile start empty for every test too.
    from jarvis.jobs import resume as resume_module, store as job_store
    for path in (job_store.DB_PATH, resume_module.PROFILE_PATH):
        if path.exists():
            path.unlink()
    yield


@pytest.fixture
def allow():
    """Answer yes to every confirmation."""
    tools.set_confirm(lambda _message: True)
    yield
    tools.set_confirm(lambda _message: False)


@pytest.fixture
def refuse():
    """Answer no to every confirmation."""
    tools.set_confirm(lambda _message: False)
    yield
