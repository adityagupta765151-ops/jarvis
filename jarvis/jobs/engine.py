"""The job-hunt pipeline, and the sentences JARVIS says about it.

Resume profile -> search -> deduplicate -> score -> store -> top ten.
Nothing here applies to anything; that lives in apply.py and always goes
through the user.
"""
from __future__ import annotations

from ..app.config import log
from . import matching, sources, store
from .resume import load_profile


def _profile_or_complaint() -> tuple[dict | None, str]:
    profile = load_profile()
    person = profile.get("candidate", {})
    if not person.get("skills"):
        return None, ("I don't have your resume yet, so I have nothing to match against. "
                      "Say: scan my resume resume.pdf")
    return profile, ""


def _query_from(profile: dict, override: str = "") -> str:
    if override.strip():
        return override.strip()
    prefs = profile.get("preferences", {})
    if prefs.get("roles"):
        return prefs["roles"][0]
    skills = profile["candidate"].get("skills", [])
    return " ".join(skills[:3]) or "software developer"


def find_jobs(query: str = "", location: str = "", limit: int = 30) -> str:
    """Search the job boards, score everything against the resume, store it."""
    profile, complaint = _profile_or_complaint()
    if not profile:
        return complaint

    search_for = _query_from(profile, query)
    where = location or (profile["preferences"].get("locations") or [""])[0]

    store.audit("search", platform="all", job=search_for, result="started")
    found, notes = sources.search(search_for, where, limit)

    if not found:
        store.audit("search", job=search_for, result="0 jobs", error="; ".join(notes))
        return (f"No jobs came back for {search_for}. Sources: {', '.join(notes)}. "
                f"If adzuna says no key, add ADZUNA_APP_ID and ADZUNA_APP_KEY to your .env.")

    ranked = matching.rank(found, profile)
    new_count = sum(1 for job in ranked if store.upsert_job(job))
    strong = [j for j in ranked if j["match_score"] >= 70]

    store.audit("search", job=search_for,
                result=f"{len(ranked)} scored, {new_count} new, {len(strong)} strong")

    lines = [f"Found {len(ranked)} jobs for {search_for}, {new_count} of them new. "
             f"{len(strong)} score 70 or above."]
    lines.append("Sources: " + ", ".join(notes))
    lines.append("")
    for i, job in enumerate(ranked[:5], 1):
        lines.append(f"{i}. {job['match_score']:>3}  {job['title']} — {job['company']} "
                     f"({job['location'] or 'location not stated'})")
    if len(ranked) > 5:
        lines.append(f"... say show my top matches for the full ten.")
    return "\n".join(lines)


def top_matches(count: int = 10, min_score: int = 0) -> str:
    """The Top 10 list, in the shape the spec asks for."""
    jobs = store.top_jobs(limit=count, min_score=min_score)
    if not jobs:
        return ("Nothing stored yet. Say find jobs for me first."
                if min_score == 0 else f"No stored job scores {min_score} or above.")

    blocks = []
    for i, job in enumerate(jobs, 1):
        applied = " (already applied)" if store.already_applied(job["job_id"]) else ""
        blocks.append("\n".join([
            f"Job #{i}   MATCH {job['match_score']}/100{applied}",
            f"  {job['title']} — {job['company']}",
            f"  {job['location'] or 'location not stated'} · {job['work_mode']} · {job['platform']}",
            f"  Salary: {job['salary'] or 'not stated'}",
            f"  You have: {', '.join(job['skills_matched']) or 'nothing listed matched'}",
            f"  Missing:  {', '.join(job['skills_missing']) or 'nothing'}",
            f"  Status:   {job['status']}",
            f"  {job['url']}",
        ]))
    return "\n\n".join(blocks)


def why_this_job(reference: str) -> str:
    """Explain one job's score. Reference can be a rank number or part of
    the company name."""
    reference = reference.strip()
    jobs = store.top_jobs(limit=25)
    if not jobs:
        return "Nothing stored yet."

    job = None
    if reference.isdigit() and 1 <= int(reference) <= len(jobs):
        job = jobs[int(reference) - 1]
    else:
        needle = reference.lower()
        job = next((j for j in jobs
                    if needle in j["company"].lower() or needle in j["title"].lower()), None)
    if not job:
        return f"I couldn't find a stored job matching '{reference}'."
    return matching.explain(job)


def missing_skills(limit: int = 10) -> str:
    """Which skills keep coming up that the resume doesn't have."""
    tally = store.missing_skill_counts(limit)
    if not tally:
        return "No jobs scored yet, so there's nothing to compare against."
    lines = ["Skills asked for most often that your resume doesn't list:"]
    for skill, count in tally:
        lines.append(f"  {skill:<20} in {count} job{'s' if count > 1 else ''}")
    return "\n".join(lines)


def open_board(board: str, query: str = "", location: str = "") -> str:
    """Open a board JARVIS isn't allowed to automate, so you can browse it."""
    import webbrowser

    profile = load_profile()
    search_for = _query_from(profile, query)
    url = sources.manual_search_url(board, search_for, location)
    if not url:
        return (f"I don't have a search link for {board}. I know linkedin, naukri, "
                f"indeed, internshala and wellfound.")
    webbrowser.open(url)
    store.audit("open_board", platform=board, job=search_for, result="opened for browsing")
    return (f"Opened {board} for {search_for}. I can't search or apply there "
            f"automatically — their terms don't allow it — so have a look yourself.")


def shortlist(reference: str) -> str:
    """Mark a job as one you want to go for."""
    jobs = store.top_jobs(limit=25)
    if reference.isdigit() and 1 <= int(reference) <= len(jobs):
        job = jobs[int(reference) - 1]
    else:
        needle = reference.lower()
        job = next((j for j in jobs if needle in j["company"].lower()), None)
    if not job:
        return f"I couldn't find '{reference}' in the stored jobs."
    store.set_status(job["job_id"], "SHORTLISTED")
    store.audit("shortlist", company=job["company"], job=job["title"], result="SHORTLISTED")
    return f"Shortlisted {job['title']} at {job['company']}."


def application_status() -> str:
    """What has actually been applied to, read from the database."""
    rows = store.applications(limit=20)
    if not rows:
        return "No applications recorded yet."
    lines = [f"{len(rows)} application record(s):"]
    for row in rows:
        when = (row["applied_at"] or "")[:16].replace("T", " ")
        lines.append(f"  {row['status']:<18} {row['company']} — {row['title']} "
                     f"{when}".rstrip())
    return "\n".join(lines)


def effectiveness() -> str:
    """The analytics, spoken rather than drawn."""
    c = store.counts()
    if not c["jobs_total"]:
        return "Nothing found yet, so there's nothing to measure."
    return "\n".join([
        f"Jobs discovered: {c['jobs_total']} ({c['jobs_today']} today)",
        f"Average match score: {c['avg_score']}",
        f"Application attempts: {c['attempts']}, submitted: {c['applied']}, "
        f"failed: {c['failed']}, needing you: {c['needs_action']}",
        f"Success rate: {c['success_rate']}%",
        f"Interviews: {c['interviews']} ({c['interview_rate']}% of submissions)",
        f"Offers: {c['offers']} ({c['offer_rate']}%)",
    ])
