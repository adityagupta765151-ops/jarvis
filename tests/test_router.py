"""The router decides what never reaches the model. A command that leaks
through costs an API call; one that is caught wrongly does the wrong thing.
Both directions are worth pinning down."""
from __future__ import annotations

import pytest

from jarvis.routing import router


class TestHandledLocally:
    @pytest.mark.parametrize("command,expect", [
        ("what's the time", "It's"),
        ("time kya hai", "It's"),
        ("what's the date", "Today is"),
        ("aaj ki date", "Today is"),
    ])
    def test_clock_questions_never_reach_the_model(self, command, expect):
        assert expect in router.fast_route(command)

    def test_remember_and_recall_work_without_the_model(self):
        assert "Noted" in router.fast_route("remember that my editor is neovim")
        assert "neovim" in router.fast_route("what do you remember")

    def test_reminders_are_set_locally(self):
        assert "08:00 PM" in router.fast_route("remind me to call mom at 8 pm")
        assert "call mom" in router.fast_route("list reminders")
        router.fast_route("cancel reminders")

    def test_searching_opens_the_browser_without_the_model(self, monkeypatch):
        opened = []
        monkeypatch.setattr(router.webbrowser, "open", opened.append)
        assert "Searching" in router.fast_route("search python internships")
        assert "google.com/search" in opened[0]

    def test_youtube_search_uses_the_youtube_url(self, monkeypatch):
        opened = []
        monkeypatch.setattr(router.webbrowser, "open", opened.append)
        router.fast_route("search react tutorials on youtube")
        assert "youtube.com/results" in opened[0]

    def test_a_known_site_opens_directly(self, monkeypatch):
        opened = []
        monkeypatch.setattr(router.webbrowser, "open", opened.append)
        assert "github" in router.fast_route("open github").lower()
        assert opened == ["https://github.com"]


class TestPassedToTheModel:
    @pytest.mark.parametrize("command", [
        "tell me a joke about cats",
        "explain what a closure is",
        "write a function that reverses a list",
        "why did that fail",
        "open the thing i was working on",
    ])
    def test_anything_needing_thought_falls_through(self, command):
        assert router.fast_route(command) is None

    def test_an_empty_command_falls_through(self):
        assert router.fast_route("   ") is None


class TestHinglish:
    def test_hinglish_open_is_understood(self, monkeypatch):
        monkeypatch.setattr(router.apps, "resolve", lambda n: "chrome")
        monkeypatch.setattr(router.apps, "open_app", lambda n: f"Opening {n}.")
        assert "Opening chrome" in router.fast_route("chrome kholo")

    def test_hinglish_close_is_understood(self, monkeypatch):
        monkeypatch.setattr(router.apps, "resolve", lambda n: "spotify")
        monkeypatch.setattr(router.apps, "close_app", lambda n: f"Closed {n}.")
        assert "Closed spotify" in router.fast_route("spotify band karo")
