"""The fast lane.

Simple commands ("open Chrome") are handled here in milliseconds, with no
model call at all. Anything this doesn't recognise falls through to the AI.
Understands plain English and common Hinglish phrasing.
"""
from __future__ import annotations

import datetime
import re
import webbrowser

from ..store import memory
from ..tools import (apps, browser, contacts, reminders, screen,
                     whatsapp, whatsapp_web)
from ..jobs import dashboard as job_dashboard, engine as jobs

SITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "linkedin": "https://www.linkedin.com",
    "instagram": "https://www.instagram.com",
    "chatgpt": "https://chat.openai.com",
    "stackoverflow": "https://stackoverflow.com",
    "leetcode": "https://leetcode.com",
    "whatsapp web": "https://web.whatsapp.com",
}

OPEN = r"(?:open|launch|start|kholo|khol do|chalu karo)"
CLOSE = r"(?:close|quit|exit|band karo|band kar do)"

# Hindi and Hinglish put the verb after the thing: "chrome kholo".
OPEN_AFTER = re.compile(r"^(.+?)\s+(?:kholo|khol do|chalu karo|open karo|start karo)\.?$", re.I)
CLOSE_AFTER = re.compile(r"^(.+?)\s+(?:band karo|band kar do|close karo|bandh karo)\.?$", re.I)


def _clean(name: str) -> str:
    return name.strip(" .,!?").removeprefix("the ").strip()


def _open_url(url: str, reply: str) -> str:
    webbrowser.open(url)
    return reply


def fast_route(command: str) -> str | None:
    """Return a reply if we can handle this locally, else None."""
    text = command.lower().strip()
    if not text:
        return None

    if re.fullmatch(r"(what(?:'s| is) the )?time.*|time kya h(?:ai)?\??", text):
        return datetime.datetime.now().strftime("It's %I:%M %p.")
    if re.fullmatch(r"(what(?:'s| is) the )?date.*|aaj ki date.*|today'?s date.*", text):
        return datetime.datetime.now().strftime("Today is %A, %d %B %Y.")

    # ------------------------------------------------ browser
    if re.fullmatch(r"(close|quit) (the )?browser.*|browser band karo.*", text):
        return browser.close_browser()

    match = re.match(r"(?:summari[sz]e|summary of) (?:this |the )?(?:page|website|site|article)"
                     r"(?: (?:at |on )?(\S+))?", text)
    if match:
        return browser.summarize_page(match.group(1))

    match = re.match(r"(?:summari[sz]e|read) (https?://\S+|www\.\S+)", text)
    if match:
        return browser.summarize_page(match.group(1))

    match = re.match(r"(?:read|padho) (?:this |the )?page.*", text)
    if match:
        return browser.read_page()

    match = re.match(r"(?:look up|research|find out(?: about)?)\s+(.+)", text)
    if match:
        return browser.search_web_and_read(_clean(match.group(1)))

    # ------------------------------------------------ screen
    if "screenshot" in text and "explain" not in text:
        return screen.take_screenshot()
    if re.search(r"(look at|read|check).*(screen|display)|screen (par|pe) kya", text):
        return screen.describe_screen()

    # ------------------------------------------------ search and sites
    match = re.search(r"(?:search|find|play)\s+(?:for\s+)?(.+?)\s+on\s+youtube", text) or \
            re.search(r"youtube\s+(?:par|pe|on)?\s*(?:search|play)?\s*(.+)", text)
    if match and "youtube" in text:
        query = _clean(match.group(1))
        if query:
            return _open_url(f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}",
                             f"Searching YouTube for {query}.")

    match = re.match(r"(?:google|search(?: for)?|dhundo)\s+(.+)", text)
    if match and "youtube" not in text:
        query = _clean(match.group(1))
        return _open_url(f"https://www.google.com/search?q={query.replace(' ', '+')}",
                         f"Searching for {query}.")

    # ------------------------------------------------ job hunting
    match = re.match(r"scan (?:my )?resume\s*(.*)", text)
    if match:
        from ..jobs import resume as resume_module
        target = _clean(match.group(1))
        return resume_module.scan_resume(target or "resume.pdf")

    if re.fullmatch(r"(show|what'?s in) (my )?(resume )?profile.*", text):
        from ..jobs import resume as resume_module
        return resume_module.show_profile()

    match = re.match(r"set (?:my )?(roles?|locations?|countr(?:y|ies)|work[ _]?modes?)"
                     r"\s+(?:to|as|=)\s+(.+)", text)
    if match:
        from ..jobs import resume as resume_module
        field = match.group(1).replace("country", "countries").rstrip("s") + "s"
        field = {"countriess": "countries", "work modes": "work_modes",
                 "workmodes": "work_modes"}.get(field, field)
        return resume_module.set_preference(field, match.group(2))

    if re.fullmatch(r"(what )?(voice|which voice).*|list voices.*|voice settings.*", text):
        from ..voice import voice_report
        return voice_report()

    if re.fullmatch(r"(open )?(my )?(job )?dashboard.*", text):
        return job_dashboard.open_dashboard()

    if re.fullmatch(r"(find|search)( me)?( today'?s)? jobs.*|find jobs for me.*", text):
        return jobs.find_jobs()

    match = re.match(r"(?:find|search) (.+?) jobs(?: in (.+))?$", text)
    if match:
        return jobs.find_jobs(_clean(match.group(1)), _clean(match.group(2) or ""))

    if re.fullmatch(r"(show )?(my )?top (matches|jobs|10|ten).*", text):
        return jobs.top_matches()

    match = re.fullmatch(r"(?:show )?jobs (?:where |with )?(?:my )?(?:match |score )?"
                         r"(?:is )?(?:above|over|at least) (\d+).*", text)
    if match:
        return jobs.top_matches(count=15, min_score=int(match.group(1)))

    match = re.match(r"why (?:did you (?:pick|select|choose) )?(?:this |job )?(.+)", text)
    if match and "job" in text:
        return jobs.why_this_job(_clean(match.group(1).replace("job", "")))

    if re.fullmatch(r"(which |what )?skills (am i |i am )?missing.*", text):
        return jobs.missing_skills()

    if re.fullmatch(r"(show )?(my )?application status.*|where (did|have) you applied.*", text):
        return jobs.application_status()

    if re.fullmatch(r"how effective.*|(show )?(my )?effectiveness.*", text):
        return jobs.effectiveness()

    match = re.match(r"(?:open|search) (linkedin|naukri|indeed|internshala|wellfound)"
                     r"(?: for (.+?))?(?: in (.+))?$", text)
    if match:
        return jobs.open_board(match.group(1), _clean(match.group(2) or ""),
                               _clean(match.group(3) or ""))

    # ------------------------------------------------ contacts
    match = re.match(r"import contacts?(?: from)?\s+(.+)", text)
    if match:
        return contacts.import_contacts(_clean(match.group(1)))
    if re.fullmatch(r"how many contacts.*|count (my )?contacts.*", text):
        return contacts.count_contacts()
    match = re.match(r"(?:find|search) contacts?\s+(?:for\s+)?(.+)", text)
    if match:
        return contacts.find_contacts(_clean(match.group(1)))

    # ------------------------------------------------ whatsapp in the browser
    if re.fullmatch(r"(open )?whatsapp web.*", text):
        return whatsapp_web.wa_open()
    if re.fullmatch(r"(list|show)( me)? (my )?(whatsapp )?(chats|contacts).*", text):
        return whatsapp_web.wa_contacts()
    if re.fullmatch(r"read (this |the )?chat.*|last messages.*", text):
        return whatsapp_web.wa_read_chat()

    match = re.search(rf"{OPEN}\s+(.+?)(?:'s)?\s*(?:chat|whatsapp chat)$", text)
    if match and "whatsapp" in text:
        return whatsapp.open_contact(_clean(match.group(1).replace("whatsapp", "")))

    match = re.match(rf"{OPEN}\s+(.+)", text) or OPEN_AFTER.match(text)
    if match:
        target = _clean(match.group(1))
        if target in SITES:
            return _open_url(SITES[target], f"Opening {target}.")
        if target.startswith(("http://", "https://", "www.")) or target.endswith((".com", ".in", ".org")):
            url = target if target.startswith("http") else f"https://{target}"
            return _open_url(url, f"Opening {target}.")
        if apps.resolve(target):
            return apps.open_app(target)
        return None  # unknown target, let the AI work it out

    match = re.match(rf"{CLOSE}\s+(.+)", text) or CLOSE_AFTER.match(text)
    if match:
        target = _clean(match.group(1))
        if apps.resolve(target):
            return apps.close_app(target)
        return None

    # ------------------------------------------------ reminders and memory
    match = re.match(r"remind me (?:to )?(.+?) (?:at|in) (.+)", text)
    if match:
        return reminders.set_reminder(_clean(match.group(1)), match.group(2))
    if re.fullmatch(r"(list|show|what are my) reminders.*", text):
        return reminders.list_reminders()
    if re.fullmatch(r"cancel (all )?reminders.*", text):
        return reminders.cancel_reminders()

    match = re.match(r"remember that (.+?) is (.+)", text)
    if match:
        return memory.remember(match.group(1), _clean(match.group(2)))
    if re.fullmatch(r"what do you remember.*", text):
        return memory.recall()

    if re.fullmatch(r"(send it|send|bhej do|haan bhej do)\.?", text):
        # Finish whichever draft is actually waiting: browser or desktop app.
        if whatsapp_web.has_draft():
            return whatsapp_web.wa_send_web()
        return whatsapp.send_whatsapp_message()

    return None
