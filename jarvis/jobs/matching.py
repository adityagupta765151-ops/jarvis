"""Scoring a job against the resume.

The score is arithmetic, not a model's opinion, so "why did you pick this
one?" always has a real answer. Every component is returned alongside the
total, and the weights are in one place where they can be argued with.
"""
from __future__ import annotations

import re

# What each part of the fit is worth. Skills dominate because that is what
# actually gets a fresher shortlisted.
WEIGHTS = {
    "skills": 45,
    "title": 20,
    "location": 15,
    "experience": 10,
    "education": 5,
    "projects": 5,
}

# However good the skill overlap, a role a fresher cannot realistically get
# should not sit at the top of the list.
REACH_CAP = 45          # senior title, or a years bar far above the candidate
ELIGIBILITY_CAP = 25    # the listing is not open to where they live
OFF_FIELD_CAP = 30      # no technology named and nothing of theirs matched

# Technologies worth spotting in a posting even when the resume lacks them,
# so "skills you are missing" is informative rather than empty.
VOCABULARY = {
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust", "php",
    "ruby", "kotlin", "swift", "sql", "html", "css", "bash",
    "react", "next.js", "nextjs", "angular", "vue", "svelte", "node.js", "nodejs",
    "express", "django", "flask", "fastapi", "spring", "spring boot", "laravel",
    "react native", "flutter", "tailwind", "bootstrap", "redux",
    "mongodb", "postgresql", "mysql", "sqlite", "redis", "firebase", "dynamodb",
    "elasticsearch", "kafka", "rabbitmq", "graphql", "rest api", "microservices",
    "aws", "azure", "gcp", "docker", "kubernetes", "jenkins", "terraform", "ansible",
    "ci/cd", "git", "github actions", "linux", "nginx",
    "machine learning", "deep learning", "nlp", "computer vision", "pytorch",
    "tensorflow", "scikit-learn", "pandas", "numpy", "opencv", "langchain", "llm",
    "data analysis", "power bi", "tableau", "excel",
    "agile", "scrum", "jira", "unit testing", "pytest", "jest", "selenium", "playwright",
}

# Titles a fresher should not be scored highly against, however well the
# keywords line up.
SENIOR = re.compile(r"\b(senior|sr\.?|lead|principal|staff|head of|manager|architect|"
                    r"director|vp|chief)\b", re.I)
JUNIOR = re.compile(r"\b(intern|internship|trainee|graduate|fresher|entry[- ]level|"
                    r"junior|jr\.?|associate|apprentice|campus)\b", re.I)
REMOTE = re.compile(r"\bremote\b|work from home|\bwfh\b", re.I)
HYBRID = re.compile(r"\bhybrid\b", re.I)

# "Remote" on a job board usually means remote within a named set of
# countries. A listing open only to the USA is not a match for someone in
# Prayagraj, however well the stack lines up.
OPEN_TO_ALL = re.compile(r"\b(worldwide|anywhere|global|any location|"
                         r"no location restriction|international)\b", re.I)

COUNTRY_WORDS = re.compile(
    r"\b(usa|u\.s\.a?|united states|canada|mexico|brazil|argentina|peru|chile|"
    r"colombia|united kingdom|uk|ireland|germany|deutschland|france|spain|italy|"
    r"portugal|netherlands|belgium|poland|sweden|norway|denmark|finland|"
    r"switzerland|austria|czech|romania|ukraine|turkey|israel|"
    r"australia|new zealand|japan|singapore|china|korea|vietnam|philippines|"
    r"indonesia|thailand|malaysia|nigeria|kenya|south africa|egypt|uae|"
    r"emea|latam|apac|europe|european union|eu)\b", re.I)

# Words that mean "and your part of the world too", whatever that is.
ANYWHERE_WORDS = ("worldwide", "anywhere", "global", "international")

YEARS = re.compile(r"(\d+)\s*(?:\+|plus)?\s*(?:-|to)?\s*(\d+)?\s*(?:years?|yrs?)\s*"
                   r"(?:of\s+)?(?:relevant\s+)?experience", re.I)


def _normalise(skill: str) -> str:
    skill = skill.lower().strip()
    return {"node": "node.js", "nodejs": "node.js", "js": "javascript",
            "ts": "typescript", "next": "next.js", "nextjs": "next.js",
            "postgres": "postgresql", "mongo": "mongodb",
            "k8s": "kubernetes", "ml": "machine learning"}.get(skill, skill)


def _mentions(text: str, skill: str) -> bool:
    """Whole-word match, so 'go' doesn't match 'good' and 'r' matches nothing."""
    if len(skill) < 2:
        return False
    return re.search(rf"(?<![\w.+#]){re.escape(skill)}(?![\w+#])", text, re.I) is not None


def skills_in(text: str, extra: set[str] | None = None) -> set[str]:
    """Skills a posting asks for, from a fixed vocabulary plus the
    candidate's own list, so their unusual skills are spotted too."""
    haystack = text.lower()
    pool = VOCABULARY | {_normalise(s) for s in (extra or set())}
    return {s for s in pool if _mentions(haystack, s)}


def _title_score(job_title: str, wanted_roles: list[str], candidate_skills: set[str]) -> tuple[int, str]:
    title = job_title.lower()

    if SENIOR.search(title) and not JUNIOR.search(title):
        return 4, "senior-level title, likely out of reach for now"

    for role in wanted_roles:
        role = role.lower().strip()
        if role and (role in title or title in role):
            return WEIGHTS["title"], f"title matches your target role ({role})"

    if JUNIOR.search(title):
        base = 15
        reason = "entry-level title"
    else:
        base = 10
        reason = "general title"

    # A title naming something the candidate actually does is worth more.
    if any(_mentions(title, s) for s in candidate_skills):
        return min(WEIGHTS["title"], base + 5), reason + " naming your stack"
    return base, reason


def can_work_there(job: dict, allowed: list[str]) -> tuple[bool, str]:
    """Is this job open to someone in one of the candidate's countries?

    A listing that names countries and doesn't name any of theirs is one
    they cannot take, whatever else fits. With no countries set, nothing is
    ruled out — silence is not a reason to discard jobs.
    """
    if not allowed:
        return True, ""

    place = f"{job.get('location', '')} {job.get('description', '')[:300]}".lower()
    if any(word in place for word in ANYWHERE_WORDS):
        return True, ""
    if any(country in place for country in allowed):
        return True, ""

    named = COUNTRY_WORDS.findall(job.get("location", ""))
    if named:
        return False, f"open to {job.get('location')}, where you can't work"
    return True, ""


def _location_score(job: dict, prefs: dict, home: str,
                    allowed: list[str]) -> tuple[int, str]:
    text = f"{job.get('location','')} {job.get('work_mode','')} {job.get('description','')[:400]}"
    wanted_modes = [m.lower() for m in prefs.get("work_modes", [])]
    wanted_places = [p.lower() for p in prefs.get("locations", []) if p.strip()]

    eligible, note = can_work_there(job, allowed)
    if not eligible:
        return 0, note

    is_remote = bool(REMOTE.search(text))
    if is_remote and ("remote" in wanted_modes or not wanted_modes):
        return WEIGHTS["location"], "remote"
    if HYBRID.search(text) and "hybrid" in wanted_modes:
        return WEIGHTS["location"], "hybrid, as you prefer"

    place = (job.get("location") or "").lower()
    for wanted in wanted_places:
        if wanted and (wanted in place or place in wanted):
            return WEIGHTS["location"], f"in {job.get('location')}"

    if home and home.lower().split(",")[0].strip() in place:
        return WEIGHTS["location"] - 2, "in your city"
    if is_remote:
        return WEIGHTS["location"] - 4, "remote, though you didn't ask for remote"
    if not wanted_places:
        return 8, "location not stated as a preference"
    return 3, f"in {job.get('location') or 'an unlisted location'}, not on your list"


def _experience_score(text: str, has_experience: bool) -> tuple[int, str]:
    match = YEARS.search(text)
    if not match:
        return 7, "no experience bar stated"
    low = int(match.group(1))
    if low <= 1:
        return WEIGHTS["experience"], f"asks for {low} year or less"
    if low == 2:
        return 6 if has_experience else 4, "asks for about 2 years"
    if low <= 4:
        return 3 if has_experience else 1, f"asks for {low}+ years"
    return 0, f"asks for {low}+ years, well above your profile"


def _allowed_countries(profile: dict) -> list[str]:
    """Countries the candidate can work in, from their stated preference or,
    failing that, the country in their own address."""
    prefs = profile.get("preferences", {})
    listed = [c.lower().strip() for c in prefs.get("countries", []) if str(c).strip()]
    if listed:
        return listed
    home = profile.get("candidate", {}).get("location", "")
    tail = home.split(",")[-1].strip().lower()
    return [tail] if tail else []


def score_job(job: dict, profile: dict) -> dict:
    """Return the job with match_score, a breakdown, and the skill lists."""
    person = profile.get("candidate", {})
    prefs = profile.get("preferences", {})

    mine = {_normalise(s) for s in
            person.get("skills", []) + person.get("languages", []) + person.get("frameworks", [])
            if s.strip()}

    text = " ".join(str(job.get(k, "")) for k in ("title", "description", "company"))
    required = skills_in(text, mine)

    matched = sorted(required & mine)
    missing = sorted(required - mine)

    if required:
        skill_points = round(WEIGHTS["skills"] * len(matched) / len(required))
        skill_note = f"{len(matched)} of {len(required)} listed skills"
    else:
        # A posting naming no technology at all is usually not a job in this
        # field: a sales or writing role reads as "no skills listed" exactly
        # like a vague engineering one. Give it little, not the benefit of
        # the doubt, and let the title argue its case instead.
        skill_points = round(WEIGHTS["skills"] * 0.15)
        skill_note = "names no technology at all"

    title_points, title_note = _title_score(job.get("title", ""), prefs.get("roles", []), mine)
    allowed = _allowed_countries(profile)
    location_points, location_note = _location_score(
        job, prefs, person.get("location", ""), allowed)
    experience_points, experience_note = _experience_score(
        text, bool(person.get("experience") or person.get("internships")))

    education_points = WEIGHTS["education"] if person.get("degree") or person.get("education") else 2
    project_points = min(WEIGHTS["projects"], len(person.get("projects", [])))

    breakdown = {
        "skills": skill_points,
        "title": title_points,
        "location": location_points,
        "experience": experience_points,
        "education": education_points,
        "projects": project_points,
    }
    total = min(100, sum(breakdown.values()))

    # Knowing the stack doesn't help if the posting filters you out before a
    # human reads it. A senior title or a years bar far above the candidate
    # caps the score, however well the skills line up, so the top ten stays
    # full of jobs that can actually be got.
    cap, reason = None, ""
    eligible, where_note = can_work_there(job, allowed)
    if not eligible:
        cap, reason = ELIGIBILITY_CAP, where_note
    elif experience_points == 0:
        cap, reason = REACH_CAP, "the experience bar is well above your profile"
    elif title_points <= 4:
        cap, reason = REACH_CAP, "a senior-level title"
    elif not required and not matched:
        # No technology named and nothing of yours matched: almost certainly
        # a job in another field that happened to come back in the search.
        cap, reason = OFF_FIELD_CAP, "nothing in it matches what you do"

    if cap is not None and total > cap:
        breakdown["capped_at"] = cap
        total = cap

    why_parts = [skill_note, title_note, location_note, experience_note]
    if cap is not None:
        why_parts.append(f"capped at {cap}: {reason}")
    if matched:
        why_parts.insert(0, "you have " + ", ".join(matched[:5]))

    job = dict(job)
    job.update({
        "match_score": total,
        "score_breakdown": breakdown,
        "skills_required": sorted(required),
        "skills_matched": matched,
        "skills_missing": missing,
        "why": "; ".join(why_parts),
    })
    return job


def rank(jobs: list[dict], profile: dict) -> list[dict]:
    """Score every job and sort best first."""
    return sorted((score_job(j, profile) for j in jobs),
                  key=lambda j: -j["match_score"])


def explain(job: dict) -> str:
    """The answer to "why did you pick this one?", in full."""
    breakdown = job.get("score_breakdown") or {}
    lines = [f"{job['title']} at {job['company']} — {job['match_score']}/100", ""]
    for part, points in breakdown.items():
        lines.append(f"  {part:<11} {points:>3} of {WEIGHTS.get(part, 0)}")
    lines.append("")
    if job.get("skills_matched"):
        lines.append("You have: " + ", ".join(job["skills_matched"]))
    if job.get("skills_missing"):
        lines.append("Missing:  " + ", ".join(job["skills_missing"]))
    if job.get("why"):
        lines.append("")
        lines.append(job["why"])
    return "\n".join(lines)
