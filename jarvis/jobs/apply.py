"""Helping with an application, without ever submitting one.

JARVIS opens the posting, fills the fields it can answer from the resume,
and then stops. The final click is yours, for three reasons: LinkedIn,
Naukri and Indeed all forbid automated submission in their terms; an
answer JARVIS guessed would be a claim made in your name; and a wrong
application cannot be taken back.

Nothing is ever written as APPLIED unless you say it was.
"""
from __future__ import annotations

from ..app.config import log
from .resume import load_profile
from .store import already_applied, audit, get_job, record_application, set_status, top_jobs

# Fields that can be answered from the resume, with the labels employers
# tend to use for them.
FIELD_MAP = {
    "name": ["full name", "your name", "name", "first name"],
    "email": ["email", "e-mail", "email address"],
    "phone": ["phone", "mobile", "contact number", "phone number"],
    "location": ["location", "city", "current location", "address"],
}

# Anything in this list is a judgement call, a legal declaration or a
# secret. JARVIS never answers these, even if it could guess.
ALWAYS_ASK = [
    "salary", "expected ctc", "current ctc", "notice period", "why do you want",
    "cover letter", "visa", "work authorization", "sponsorship", "relocate",
    "gender", "race", "ethnicity", "disability", "veteran", "date of birth",
    "captcha", "otp", "verification code", "password", "consent", "declare",
    "certify", "agree to", "references",
]


def _resolve(reference: str) -> dict | None:
    """Accept a rank number from the top list, or part of a company name."""
    reference = (reference or "").strip()
    jobs = top_jobs(limit=25)
    if not jobs:
        return None
    if reference.isdigit() and 1 <= int(reference) <= len(jobs):
        return jobs[int(reference) - 1]
    needle = reference.lower()
    return next((j for j in jobs
                 if needle in j["company"].lower() or needle in j["title"].lower()), None)


def prepare_application(reference: str) -> str:
    """Open a job and fill in what the resume can answer. Does not submit."""
    from ..tools import browser

    job = _resolve(reference)
    if not job:
        return f"I couldn't find '{reference}' in the stored jobs. Say show my top matches."

    if already_applied(job["job_id"]):
        return (f"You already applied to {job['title']} at {job['company']}. "
                f"I won't open a duplicate.")

    if not job["url"]:
        set_status(job["job_id"], "NEEDS_USER_ACTION")
        return f"{job['company']} has no application link stored, so I can't open it."

    profile = load_profile()
    person = profile.get("candidate", {})

    opened = browser.open_page(job["url"])
    if not opened.startswith("Opened"):
        record_application(job["job_id"], "APPLICATION_FAILED", source="browser",
                           notes=opened)
        audit("prepare", platform=job["platform"], company=job["company"],
              job=job["title"], result="failed", error=opened)
        return f"I couldn't open the posting: {opened}"

    filled: list[str] = []
    for field, labels in FIELD_MAP.items():
        value = person.get(field, "")
        if not value:
            continue
        for label in labels:
            result = browser.fill_field(label, value)
            if result.startswith("Filled"):
                filled.append(f"{field} = {value}")
                break

    page = browser.read_page()
    asks_for = [phrase for phrase in ALWAYS_ASK if phrase in page.lower()]

    set_status(job["job_id"], "NEEDS_USER_ACTION" if asks_for else "READY_TO_APPLY")
    audit("prepare", platform=job["platform"], company=job["company"], job=job["title"],
          result=f"filled {len(filled)} fields")

    lines = [
        f"{job['title']} at {job['company']} — match {job['match_score']}/100",
        f"{job['url']}",
        "",
        f"Resume on file: {profile.get('source_file') or 'none'}",
    ]
    lines.append("Filled in: " + (", ".join(filled) if filled
                                  else "nothing — I couldn't find fields I could answer"))
    if asks_for:
        lines.append("")
        lines.append("This form asks things I won't answer for you: "
                     + ", ".join(sorted(set(asks_for))[:6]) + ".")
    lines.append("")
    lines.append("The page is open. Check every field, attach your resume, and press "
                 "submit yourself. Then tell me: mark 1 as applied.")
    return "\n".join(lines)


def mark_applied(reference: str, notes: str = "") -> str:
    """Record that you submitted an application. Only you can say this."""
    job = _resolve(reference)
    if not job:
        return f"I couldn't find '{reference}' in the stored jobs."
    if already_applied(job["job_id"]):
        return f"That one is already recorded as applied."

    application_id = record_application(job["job_id"], "APPLIED",
                                        source=job["platform"], notes=notes)
    audit("applied", platform=job["platform"], company=job["company"], job=job["title"],
          result="recorded", application_id=application_id)
    return f"Recorded: applied to {job['title']} at {job['company']}."


def mark_status(reference: str, status: str) -> str:
    """Move a job along: interview, rejected, offer, withdrawn."""
    from .store import STATUSES

    status = status.upper().strip().replace(" ", "_")
    if status not in STATUSES:
        return f"Status must be one of: {', '.join(s.lower() for s in STATUSES)}."

    job = _resolve(reference)
    if not job:
        return f"I couldn't find '{reference}' in the stored jobs."

    set_status(job["job_id"], status)
    audit("status", company=job["company"], job=job["title"], result=status)
    return f"{job['company']} — {job['title']} is now {status.replace('_', ' ').lower()}."


def upload_resume_to_form(path: str = "") -> str:
    """Attach the resume file to the open application form."""
    from ..tools import browser

    profile = load_profile()
    filename = path or profile.get("source_file", "")
    if not filename:
        return "I don't know which resume file to attach. Scan one first."
    return ("I can't attach files to a form for you — the browser blocks scripted "
            f"file pickers. Attach {filename} yourself; the page is open.")
