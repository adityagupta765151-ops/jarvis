"""Reading a resume into a structured profile.

Takes a PDF, a Word file or a photo of a printed resume, pulls the text
out, and has the model turn it into fields. Nothing is invented: if the
resume doesn't say it, the field stays empty, because every later step
(matching, filling application forms) treats this profile as the only
truth about the candidate.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..app.config import MEMORY_DIR, log
from ..ai.provider import ask_about_image, ask_text

PROFILE_PATH = MEMORY_DIR / "resume_profile.json"

EMPTY_PROFILE = {
    "candidate": {
        "name": "", "email": "", "phone": "", "location": "",
        "education": [], "graduation_year": "", "degree": "",
        "skills": [], "languages": [], "frameworks": [],
        "projects": [], "experience": [], "internships": [], "certifications": [],
    },
    "preferences": {"roles": [], "locations": [], "work_modes": [], "countries": []},
    "source_file": "",
    "raw_text_chars": 0,
}

EXTRACT_PROMPT = """Read this resume and return the facts it contains as JSON.

Return exactly this shape, with no commentary and no markdown fence:

{{
  "candidate": {{
    "name": "", "email": "", "phone": "", "location": "",
    "education": ["degree, institution, year"],
    "graduation_year": "", "degree": "",
    "skills": [], "languages": [], "frameworks": [],
    "projects": ["name - one line"],
    "experience": ["role, company, dates"],
    "internships": ["role, company, dates"],
    "certifications": []
  }},
  "preferences": {{ "roles": [], "locations": [], "work_modes": [], "countries": [] }}
}}

Rules that matter more than completeness:
- Only write what the resume actually says. Leave a field empty rather than guessing.
- "languages" means programming languages. "frameworks" means libraries and frameworks.
- "roles" under preferences: job titles this person is plainly aiming for, drawn from
  the resume's own objective or the roles they have held. If it doesn't say, leave empty.
- "work_modes" only if stated, one of remote, hybrid, onsite.
- "countries": countries the resume says they can work in. If it doesn't say,
  put the country of their own address, or leave empty.

Resume text:
{text}"""


def _from_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:10])
    except Exception as e:  # noqa: BLE001
        log(f"resume pdf read failed: {e}")
        return ""


def _from_docx(path: Path) -> str:
    try:
        import docx
    except ImportError:
        return ""
    try:
        return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    except Exception as e:  # noqa: BLE001
        log(f"resume docx read failed: {e}")
        return ""


def _from_image(path: Path) -> str:
    """Local OCR first; the model's own vision is the fallback, since it
    reads a photographed resume better than Tesseract usually does."""
    try:
        import pytesseract
        from PIL import Image
        text = pytesseract.image_to_string(Image.open(path))
        if len(text.strip()) > 120:
            return text
    except Exception as e:  # noqa: BLE001
        log(f"tesseract unavailable or failed: {e}")
    try:
        return ask_about_image(
            path.read_bytes(),
            "Transcribe every word of this resume as plain text. No commentary.")
    except Exception as e:  # noqa: BLE001
        log(f"vision transcription failed: {e}")
        return ""


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _from_pdf(path)
        # A scanned PDF has pages but almost no extractable text.
        return text if len(text.strip()) > 120 else _from_image(path)
    if suffix in (".docx", ".doc"):
        return _from_docx(path)
    if suffix in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        return _from_image(path)
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    return ""


def _parse_json(raw: str) -> dict | None:
    """Models sometimes wrap JSON in a fence or add a sentence."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    match = re.search(r"\{.*\}", cleaned, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        log(f"resume json parse failed: {e}")
        return None


def _merge(parsed: dict, source: str, chars: int) -> dict:
    """Keep the known shape whatever the model returns, so later code can
    rely on every key existing."""
    profile = json.loads(json.dumps(EMPTY_PROFILE))
    for section in ("candidate", "preferences"):
        for key, default in profile[section].items():
            value = (parsed.get(section) or {}).get(key, default)
            if isinstance(default, list):
                profile[section][key] = [str(v).strip() for v in value if str(v).strip()] \
                    if isinstance(value, list) else []
            else:
                profile[section][key] = str(value).strip() if value else ""
    profile["source_file"] = source
    profile["raw_text_chars"] = chars
    return profile


def load_profile() -> dict:
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return json.loads(json.dumps(EMPTY_PROFILE))


def save_profile(profile: dict) -> None:
    PROFILE_PATH.write_text(json.dumps(profile, indent=2, ensure_ascii=False),
                            encoding="utf-8")


SEARCH_FOLDERS = ("Downloads", "Documents", "Desktop", "OneDrive/Documents")
RESUME_SUFFIXES = (".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".md")


def find_resume_file(name: str) -> Path | None:
    """Find the file the user means, forgivingly.

    Windows hides known extensions, so someone reading "aditya-resume.pdf"
    off the screen may be looking at a file actually called
    aditya-resume.pdf.pdf. Case varies too. So the stem is matched rather
    than the exact name, across the folders a resume normally lives in.
    """
    given = Path(name).expanduser()
    if given.exists():
        return given

    def base(name: str) -> str:
        """Strip every known extension, so aditya-resume.pdf.pdf,
        aditya-resume.pdf and aditya-resume all reduce to one key."""
        name = name.lower()
        changed = True
        while changed:
            changed = False
            for suffix in RESUME_SUFFIXES:
                if name.endswith(suffix):
                    name = name[: -len(suffix)]
                    changed = True
        return name

    wanted = given.name.lower()
    stem = base(given.name)
    folders = [Path.home() / f for f in SEARCH_FOLDERS] + [MEMORY_DIR, Path.cwd()]

    for folder in folders:
        if not folder.is_dir():
            continue
        try:
            entries = list(folder.iterdir())
        except OSError:
            continue

        for entry in entries:                       # exact name, any case
            if entry.is_file() and entry.name.lower() == wanted:
                return entry
        for entry in entries:                       # same base name, any extension
            if (entry.is_file() and entry.suffix.lower() in RESUME_SUFFIXES
                    and base(entry.name) == stem):
                return entry
    return None


def list_candidate_resumes(limit: int = 6) -> list[str]:
    """Files that look like a resume, to suggest when the name was wrong."""
    found: list[str] = []
    for folder_name in SEARCH_FOLDERS:
        folder = Path.home() / folder_name
        if not folder.is_dir():
            continue
        try:
            for entry in sorted(folder.iterdir(), key=lambda p: -p.stat().st_mtime):
                if (entry.is_file() and entry.suffix.lower() in RESUME_SUFFIXES
                        and re.search(r"resume|cv|curriculum", entry.stem, re.I)):
                    found.append(entry.name)
                    if len(found) >= limit:
                        return found
        except OSError:
            continue
    return found


def scan_resume(path: str) -> str:
    """Read a resume file and build the candidate profile from it."""
    file = find_resume_file(path)
    if file is None:
        suggestions = list_candidate_resumes()
        if suggestions:
            return ("I couldn't find " + path + ". These look like resumes: "
                    + ", ".join(suggestions) + ". Say: scan my resume <one of those>")
        return (f"I couldn't find {path}, and nothing resume-shaped is in your "
                f"Downloads, Documents or Desktop.")

    text = extract_text(file)
    if len(text.strip()) < 120:
        return ("I couldn't get readable text out of that file. If it's a scan, "
                "install Tesseract OCR, or export the resume as a PDF with real text.")

    try:
        raw = ask_text(EXTRACT_PROMPT.format(text=text[:18000]))
    except RuntimeError as e:
        return str(e)

    parsed = _parse_json(raw)
    if not parsed:
        return "I read the resume but couldn't structure it. Try again in a moment."

    profile = _merge(parsed, file.name, len(text))
    save_profile(profile)

    person = profile["candidate"]
    return (f"Read {file.name}. Profile saved for {person['name'] or 'you'}: "
            f"{len(person['skills'])} skills, {len(person['projects'])} projects, "
            f"{len(person['education'])} education entries.")


def show_profile() -> str:
    """What JARVIS currently believes about the candidate."""
    profile = load_profile()
    person = profile["candidate"]
    if not person["name"] and not person["skills"]:
        return "No resume has been scanned yet. Say: scan my resume resume.pdf"

    lines = [f"Name: {person['name'] or 'not stated'}",
             f"Degree: {person['degree'] or 'not stated'} ({person['graduation_year'] or '-'})",
             f"Location: {person['location'] or 'not stated'}",
             f"Skills ({len(person['skills'])}): {', '.join(person['skills'][:18])}"]
    if person["projects"]:
        lines.append(f"Projects: {len(person['projects'])}")
    if profile["preferences"]["roles"]:
        lines.append(f"Target roles: {', '.join(profile['preferences']['roles'])}")
    return "\n".join(lines)


FIELDS = ("roles", "locations", "work_modes", "countries")


def set_preference(field: str, value: str) -> str:
    """Set a job-search preference the resume didn't state."""
    field = field.lower().strip().replace(" ", "_")
    field = {"role": "roles", "location": "locations", "country": "countries",
             "work_mode": "work_modes", "mode": "work_modes"}.get(field, field)
    if field not in FIELDS:
        return "I can set roles, locations, countries or work_modes."

    profile = load_profile()
    profile["preferences"].setdefault(field, [])
    profile["preferences"][field] = [v.strip() for v in value.split(",") if v.strip()]
    save_profile(profile)

    note = ""
    if field == "countries":
        note = (" Jobs open only to other countries will be scored down, "
                "since you couldn't take them.")
    return f"Noted. {field}: {', '.join(profile['preferences'][field])}.{note}"


def countries() -> list[str]:
    """Where the candidate can actually work. Falls back to the country in
    their own address, so this is never empty in practice."""
    profile = load_profile()
    listed = [c.lower().strip() for c in profile["preferences"].get("countries", []) if c.strip()]
    if listed:
        return listed
    home = profile["candidate"].get("location", "")
    tail = home.split(",")[-1].strip().lower()
    return [tail] if tail else []
