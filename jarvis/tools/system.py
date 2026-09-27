"""Shell commands, the editor, the browser and what machine this is."""
from __future__ import annotations

import datetime
import os
import platform
import shutil
import subprocess
import webbrowser

from ..app.config import WORKSPACE
from .permissions import confirm
from .workspace import clip, safe_path


def run_command(command: str, cwd: str = ".") -> str:
    """Run a shell command. Always asks first."""
    folder = safe_path(cwd)
    if not confirm(f"Run this command in {folder}?\n\n{command}"):
        return "You declined, so the command didn't run."
    try:
        result = subprocess.run(command, shell=True, cwd=folder,
                                capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return "The command took too long and was stopped after five minutes."
    output = (result.stdout + ("\n" + result.stderr if result.stderr else "")).strip()
    return clip(f"Exit code {result.returncode}\n{output or '(no output)'}")


def open_in_vscode(path: str = ".", line: int | None = None) -> str:
    """Open a file or folder in VS Code, optionally at a line."""
    p = safe_path(path)
    code = shutil.which("code")
    if not code:
        return "VS Code's 'code' command isn't on PATH, so I can't open files in it."
    target = f"{p}:{line}" if line and p.is_file() else str(p)
    subprocess.Popen([code, "-g", target], shell=(os.name == "nt"))
    return f"Opened {p.name} in VS Code."


def open_url(url: str) -> str:
    """Open a website in the normal browser. Nothing is read back."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url}."


def search_web(query: str) -> str:
    """Open a Google search. The results are not read."""
    webbrowser.open(f"https://www.google.com/search?q={query.replace(' ', '+')}")
    return f"Searching the web for {query}."


def get_datetime() -> str:
    return datetime.datetime.now().strftime("%A, %d %B %Y, %I:%M %p")


def get_system_info() -> str:
    return (f"{platform.system()} {platform.release()}, "
            f"Python {platform.python_version()}, workspace {WORKSPACE}")
