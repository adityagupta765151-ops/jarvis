"""Browser automation.

One browser stays open in the background, so the first page costs a few
seconds and every page after that is quick. Playwright's objects belong to
the thread that made them, and JARVIS answers commands on whatever thread
is free, so everything here is funnelled onto one worker thread.

Reading pages is safe and never asks. Clicking and typing ask first when
the target looks like it pays, buys, deletes or submits something.
"""
from __future__ import annotations

import queue
import re
import threading

from ..app.config import BROWSER_HEADLESS, BROWSER_PROFILE, log
from ..ai.provider import ask_text

MAX_TEXT = 12000          # characters of page text handed to the model
SETUP_HINT = ("Browser automation needs Playwright. In the JARVIS folder run: "
              "pip install playwright, then playwright install chromium.")

# A click on any of these gets a confirmation dialog first.
SENSITIVE = re.compile(
    r"\b(pay|payment|buy|purchase|checkout|order|subscribe|donate|"
    r"delete|remove|deactivate|close account|unsubscribe|"
    r"submit|send|confirm|place order|book now|apply now)\b", re.I)


class _Worker:
    """Owns Playwright on a single thread and runs jobs sent to it."""

    def __init__(self) -> None:
        self.jobs: queue.Queue = queue.Queue()
        self.thread: threading.Thread | None = None
        self.playwright = None
        self.context = None
        self.page = None
        self.lock = threading.Lock()

    def _ensure_thread(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self) -> None:
        while True:
            job, box, done = self.jobs.get()
            try:
                box.append(job())
            except Exception as e:  # noqa: BLE001
                log(f"browser job failed: {type(e).__name__}: {e}")
                box.append(_friendly(e))
            finally:
                done.set()

    def run(self, job) -> str:
        """Hand a job to the browser thread and wait for its answer."""
        with self.lock:
            self._ensure_thread()
            box: list = []
            done = threading.Event()
            self.jobs.put((job, box, done))
            if not done.wait(timeout=180):
                return "The browser took too long and I gave up on that step."
            return box[0] if box else "The browser returned nothing."

    # -------------------------------------------------- on the worker thread

    def start(self):
        """Launch the browser once, then keep it alive."""
        if self.context:
            return self.context
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError(SETUP_HINT) from e

        self.playwright = sync_playwright().start()
        BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)

        # Try Playwright's own Chromium first, then fall back to the Chrome or
        # Edge already on the machine, so a failed 150 MB download isn't fatal.
        # A persistent profile of our own keeps logins between sessions without
        # touching the browser profile you use yourself.
        options = dict(
            headless=BROWSER_HEADLESS,
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        problems = []
        for channel in (None, "chrome", "msedge"):
            try:
                extra = {"channel": channel} if channel else {}
                self.context = self.playwright.chromium.launch_persistent_context(
                    str(BROWSER_PROFILE), **options, **extra)
                log(f"browser started ({channel or 'bundled chromium'})")
                break
            except Exception as e:  # noqa: BLE001
                problems.append(f"{channel or 'bundled'}: {str(e)[:80]}")
        else:
            log("no browser could start: " + " | ".join(problems))
            raise RuntimeError(
                "I couldn't start a browser. Either install Google Chrome, or run "
                "python -m playwright install chromium in the JARVIS folder.")

        self.context.set_default_timeout(20000)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        return self.context

    def current(self):
        self.start()
        if self.page is None or self.page.is_closed():
            self.page = self.context.new_page()
        return self.page

    def shutdown(self) -> str:
        if self.context:
            try:
                self.context.close()
            except Exception as e:  # noqa: BLE001
                log(f"context close failed: {e}")
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception as e:  # noqa: BLE001
                log(f"playwright stop failed: {e}")
        self.context = self.page = self.playwright = None
        return "Browser closed."


_worker = _Worker()


def _friendly(error: Exception) -> str:
    """Turn a Playwright exception into something worth saying out loud."""
    text = str(error)
    if SETUP_HINT in text:
        return SETUP_HINT
    name = type(error).__name__
    if "Timeout" in name or "Timeout" in text:
        return "The page took too long to respond. It may be slow or the element isn't there."
    if "net::ERR_NAME_NOT_RESOLVED" in text:
        return "That address doesn't exist. Check the spelling."
    if "net::ERR_INTERNET_DISCONNECTED" in text:
        return "I can't reach the internet right now."
    if "closed" in text.lower():
        return "The browser window was closed. Ask me again and I'll reopen it."
    return f"The browser hit a problem: {text[:160]}"


def _ask(prompt: str) -> str:
    """Ask the model about a page, turning an outage into a sentence
    rather than an exception the user would never understand."""
    try:
        return ask_text(prompt)
    except RuntimeError as e:
        return str(e)


def _tidy(url: str) -> str:
    """Add https:// to a bare address, but leave a real scheme alone."""
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    return url


def _page_text(page) -> str:
    """Visible text only. Scripts, styles and nav chrome are dropped."""
    text = page.evaluate("""() => {
        const drop = ['script', 'style', 'noscript', 'svg', 'nav', 'footer', 'aside'];
        const clone = document.body.cloneNode(true);
        drop.forEach(tag => clone.querySelectorAll(tag).forEach(n => n.remove()));
        const main = clone.querySelector('main, article, [role=main]') || clone;
        return main.innerText;
    }""")
    text = re.sub(r"\n{3,}", "\n\n", text or "").strip()
    return text[:MAX_TEXT]


# ---------------------------------------------------------------- the tools

def open_page(url: str) -> str:
    """Open a web page in JARVIS's own browser."""
    def job():
        page = _worker.current()
        page.goto(_tidy(url), wait_until="domcontentloaded")
        return f"Opened {page.title() or url}."
    return _worker.run(job)


GOT_TEXT = "\x01"   # the worker prefixes real page content with this


def _read(url: str | None) -> tuple[bool, str]:
    """Returns (did we get page text?, the text or the reason why not)."""
    def job():
        page = _worker.current()
        if url:
            page.goto(_tidy(url), wait_until="domcontentloaded")
            page.wait_for_timeout(600)
        if page.url in ("about:blank", ""):
            return "No page is open yet. Give me a web address and I'll read it."
        text = _page_text(page)
        if not text:
            return "That page had no readable text. It may load its content with a script."
        return f"{GOT_TEXT}{page.title()}\n\n{text}"

    result = _worker.run(job)
    if result.startswith(GOT_TEXT):
        return True, result[len(GOT_TEXT):]
    return False, result


def read_page(url: str | None = None) -> str:
    """Read the visible text of a page. Give a url, or leave it out for
    whatever page is already open."""
    return _read(url)[1]


def summarize_page(url: str | None = None, question: str | None = None) -> str:
    """Read a page and summarise it, or answer a question about it."""
    ok, body = _read(url)
    if not ok:
        return body
    ask = question or "Summarise this page in four or five plain sentences."
    return _ask(f"{ask}\n\nPage content:\n{body}")


def search_web_and_read(query: str, count: int = 5) -> str:
    """Search the web and bring back the top results with their snippets,
    instead of just opening a tab."""
    def job():
        page = _worker.current()
        page.goto("https://duckduckgo.com/?q=" + query.replace(" ", "+"),
                  wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        results = page.evaluate("""(n) => {
            const out = [];
            const seen = new Set();
            document.querySelectorAll('a[href^="http"]').forEach(a => {
                const title = (a.innerText || '').trim();
                if (title.length < 15 || seen.has(a.href)) return;
                if (a.href.includes('duckduckgo.com')) return;
                seen.add(a.href);
                if (out.length < n) out.push(title + ' - ' + a.href);
            });
            return out;
        }""", count)
        if not results:
            return f"I searched for {query} but couldn't read any results."
        return f"Top results for {query}:\n" + "\n".join(results)
    return _worker.run(job)


def find_on_page(what: str) -> str:
    """Ask what's on the page: a price, a heading, a button, a date."""
    ok, body = _read(None)
    if not ok:
        return body
    return _ask(
        f"From this page, find: {what}. Answer in one short sentence. "
        f"If it isn't there, say so plainly.\n\nPage content:\n{body}")


def click_text(text: str) -> str:
    """Click a link or button by the words on it. Asks first if the click
    looks like it spends money or changes something."""
    from .tools import confirm_fn

    if SENSITIVE.search(text):
        if not confirm_fn(f"Click \"{text}\" on this page?\n\n"
                          f"This looks like it could submit, send, buy or delete something."):
            return "You declined, so I didn't click it."

    def job():
        page = _worker.current()
        # Look by role first, the way a person reads the page, so a change
        # of styling or class names doesn't break it.
        for finder in (
            lambda: page.get_by_role("button", name=text, exact=False),
            lambda: page.get_by_role("link", name=text, exact=False),
            lambda: page.get_by_text(text, exact=False),
        ):
            target = finder().first
            if target.count() > 0:
                target.click()
                page.wait_for_timeout(1200)
                return f"Clicked {text}. Now on: {page.title()}"
        return f"I couldn't find anything labelled \"{text}\" on this page."
    return _worker.run(job)


def fill_field(label: str, value: str) -> str:
    """Type into a form field, found by its label or placeholder."""
    def job():
        page = _worker.current()
        for finder in (
            lambda: page.get_by_label(label, exact=False),
            lambda: page.get_by_placeholder(label, exact=False),
            lambda: page.locator(f"input[name*='{label}' i], textarea[name*='{label}' i]"),
        ):
            target = finder().first
            if target.count() > 0:
                target.fill(value)
                return f"Filled {label}."
        return f"I couldn't find a field called \"{label}\" on this page."
    return _worker.run(job)


def press_key(key: str = "Enter") -> str:
    """Press a key, usually Enter to submit a search box."""
    def job():
        page = _worker.current()
        page.keyboard.press(key)
        page.wait_for_timeout(1200)
        return f"Pressed {key}. Now on: {page.title()}"
    return _worker.run(job)


def browser_screenshot() -> str:
    """Save a picture of the current page."""
    from ..app.config import MEMORY_DIR
    import datetime

    def job():
        page = _worker.current()
        path = MEMORY_DIR / datetime.datetime.now().strftime("page-%H%M%S.png")
        page.screenshot(path=str(path), full_page=False)
        return f"Saved a picture of the page to {path}."
    return _worker.run(job)


def close_browser() -> str:
    """Shut the automated browser down and free its memory."""
    return _worker.run(_worker.shutdown)
