"""Where jobs, applications and the audit trail live.

One SQLite file under memory/. Plain SQL rather than an ORM, because the
schema is small and readable this way, and the file can be opened with any
SQLite viewer if something looks wrong.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import sqlite3
import threading
from typing import Any

from ..app.config import MEMORY_DIR, log

DB_PATH = MEMORY_DIR / "jobs.db"

STATUSES = ("FOUND", "SHORTLISTED", "READY_TO_APPLY", "APPLIED", "APPLICATION_FAILED",
            "NEEDS_USER_ACTION", "REJECTED", "INTERVIEW", "OFFER", "WITHDRAWN")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id           TEXT PRIMARY KEY,
    company          TEXT NOT NULL,
    title            TEXT NOT NULL,
    location         TEXT,
    work_mode        TEXT,
    salary           TEXT,
    platform         TEXT,
    url              TEXT,
    description      TEXT,
    match_score      INTEGER DEFAULT 0,
    score_breakdown  TEXT,
    skills_required  TEXT,
    skills_matched   TEXT,
    skills_missing   TEXT,
    why              TEXT,
    discovered_at    TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'FOUND'
);

CREATE TABLE IF NOT EXISTS applications (
    application_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL REFERENCES jobs(job_id),
    applied_at      TEXT,
    resume_version  TEXT,
    status          TEXT NOT NULL,
    source          TEXT,
    confirmation_id TEXT,
    notes           TEXT,
    follow_up_date  TEXT
);

CREATE TABLE IF NOT EXISTS audit (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT NOT NULL,
    action         TEXT NOT NULL,
    platform       TEXT,
    company        TEXT,
    job            TEXT,
    result         TEXT,
    error          TEXT,
    application_id INTEGER
);

CREATE INDEX IF NOT EXISTS jobs_score ON jobs(match_score DESC);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
"""

_lock = threading.Lock()


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def job_id_for(company: str, title: str, url: str = "") -> str:
    """The same posting listed on two boards should collapse into one row.

    Company and title decide identity, normalised hard enough that
    "Google India Pvt Ltd" and "Google" don't count as different, and the
    URL is deliberately ignored.
    """
    def squash(text: str) -> str:
        text = (text or "").lower()
        text = re.sub(r"\b(pvt|private|ltd|limited|inc|llp|technologies|technology|"
                      r"solutions|services|india|labs|systems)\b", " ", text)
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return " ".join(text.split())

    key = f"{squash(company)}|{squash(title)}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def upsert_job(job: dict) -> bool:
    """Store a job. Returns True if it was new, False if already known.

    An existing row keeps its status and application history; only the
    scoring and the description are refreshed.
    """
    with _lock:
        conn = connect()
        try:
            existing = conn.execute("SELECT job_id FROM jobs WHERE job_id = ?",
                                    (job["job_id"],)).fetchone()
            if existing:
                conn.execute("""
                    UPDATE jobs SET match_score = ?, score_breakdown = ?,
                        skills_required = ?, skills_matched = ?, skills_missing = ?,
                        why = ?, description = COALESCE(NULLIF(?, ''), description)
                    WHERE job_id = ?""",
                    (job.get("match_score", 0), json.dumps(job.get("score_breakdown", {})),
                     json.dumps(job.get("skills_required", [])),
                     json.dumps(job.get("skills_matched", [])),
                     json.dumps(job.get("skills_missing", [])),
                     job.get("why", ""), job.get("description", ""), job["job_id"]))
                conn.commit()
                return False

            conn.execute("""
                INSERT INTO jobs (job_id, company, title, location, work_mode, salary,
                    platform, url, description, match_score, score_breakdown,
                    skills_required, skills_matched, skills_missing, why,
                    discovered_at, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job["job_id"], job["company"], job["title"], job.get("location", ""),
                 job.get("work_mode", ""), job.get("salary", ""), job.get("platform", ""),
                 job.get("url", ""), job.get("description", ""), job.get("match_score", 0),
                 json.dumps(job.get("score_breakdown", {})),
                 json.dumps(job.get("skills_required", [])),
                 json.dumps(job.get("skills_matched", [])),
                 json.dumps(job.get("skills_missing", [])),
                 job.get("why", ""), _now(), "FOUND"))
            conn.commit()
            return True
        finally:
            conn.close()


def _row_to_job(row: sqlite3.Row) -> dict:
    job = dict(row)
    for field in ("skills_required", "skills_matched", "skills_missing", "score_breakdown"):
        try:
            job[field] = json.loads(job[field] or ("{}" if field == "score_breakdown" else "[]"))
        except json.JSONDecodeError:
            job[field] = {} if field == "score_breakdown" else []
    return job


def top_jobs(limit: int = 10, min_score: int = 0, status: str | None = None) -> list[dict]:
    conn = connect()
    try:
        sql = "SELECT * FROM jobs WHERE match_score >= ?"
        params: list[Any] = [min_score]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY match_score DESC, discovered_at DESC LIMIT ?"
        params.append(limit)
        return [_row_to_job(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def get_job(job_id: str) -> dict | None:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None
    finally:
        conn.close()


def set_status(job_id: str, status: str) -> bool:
    if status not in STATUSES:
        return False
    with _lock:
        conn = connect()
        try:
            conn.execute("UPDATE jobs SET status = ? WHERE job_id = ?", (status, job_id))
            conn.commit()
            return conn.total_changes > 0
        finally:
            conn.close()


def record_application(job_id: str, status: str, source: str = "",
                       notes: str = "", confirmation_id: str = "") -> int:
    """A row here means an application was really attempted. Nothing writes
    APPLIED unless the user confirmed the submission themselves."""
    with _lock:
        conn = connect()
        try:
            cursor = conn.execute("""
                INSERT INTO applications (job_id, applied_at, resume_version, status,
                    source, confirmation_id, notes)
                VALUES (?,?,?,?,?,?,?)""",
                (job_id, _now() if status == "APPLIED" else None,
                 _resume_version(), status, source, confirmation_id, notes))
            conn.execute("UPDATE jobs SET status = ? WHERE job_id = ?", (status, job_id))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()


def _resume_version() -> str:
    from .resume import PROFILE_PATH
    if not PROFILE_PATH.exists():
        return "none"
    stamp = datetime.datetime.fromtimestamp(PROFILE_PATH.stat().st_mtime)
    return stamp.strftime("%Y%m%d-%H%M")


def already_applied(job_id: str) -> bool:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM applications WHERE job_id = ? AND status = 'APPLIED' LIMIT 1",
            (job_id,)).fetchone()
        return row is not None
    finally:
        conn.close()


def applications(limit: int = 50) -> list[dict]:
    conn = connect()
    try:
        return [dict(r) for r in conn.execute("""
            SELECT a.*, j.company, j.title, j.platform, j.url, j.match_score, j.location
            FROM applications a JOIN jobs j ON j.job_id = a.job_id
            ORDER BY a.application_id DESC LIMIT ?""", (limit,))]
    finally:
        conn.close()


def audit(action: str, platform: str = "", company: str = "", job: str = "",
          result: str = "", error: str = "", application_id: int | None = None) -> None:
    """Every action leaves a trace, successful or not."""
    try:
        with _lock:
            conn = connect()
            try:
                conn.execute("""INSERT INTO audit (timestamp, action, platform, company,
                                job, result, error, application_id) VALUES (?,?,?,?,?,?,?,?)""",
                             (_now(), action, platform, company, job, result, error, application_id))
                conn.commit()
            finally:
                conn.close()
    except Exception as e:  # noqa: BLE001  (logging must never break the task)
        log(f"audit write failed: {e}")


def audit_trail(limit: int = 60) -> list[dict]:
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))]
    finally:
        conn.close()


def counts() -> dict:
    """The numbers the dashboard shows. All read, none estimated."""
    conn = connect()
    try:
        def scalar(sql: str, params: tuple = ()) -> int:
            return conn.execute(sql, params).fetchone()[0] or 0

        today = datetime.date.today().isoformat()
        by_status = {row["status"]: row["n"] for row in conn.execute(
            "SELECT status, COUNT(*) n FROM jobs GROUP BY status")}

        attempts = scalar("SELECT COUNT(*) FROM applications")
        applied = scalar("SELECT COUNT(*) FROM applications WHERE status = 'APPLIED'")
        interviews = scalar("SELECT COUNT(*) FROM jobs WHERE status = 'INTERVIEW'")
        offers = scalar("SELECT COUNT(*) FROM jobs WHERE status = 'OFFER'")

        return {
            "jobs_total": scalar("SELECT COUNT(*) FROM jobs"),
            "jobs_today": scalar("SELECT COUNT(*) FROM jobs WHERE discovered_at LIKE ?",
                                 (f"{today}%",)),
            "by_status": by_status,
            "attempts": attempts,
            "applied": applied,
            "failed": scalar("SELECT COUNT(*) FROM applications WHERE status = 'APPLICATION_FAILED'"),
            "needs_action": by_status.get("NEEDS_USER_ACTION", 0),
            "interviews": interviews,
            "offers": offers,
            "rejected": by_status.get("REJECTED", 0),
            "success_rate": round(applied / attempts * 100) if attempts else 0,
            "interview_rate": round(interviews / applied * 100) if applied else 0,
            "offer_rate": round(offers / applied * 100) if applied else 0,
            "avg_score": round(conn.execute(
                "SELECT AVG(match_score) FROM jobs").fetchone()[0] or 0),
            "by_platform": {r["platform"] or "unknown": r["n"] for r in conn.execute(
                "SELECT platform, COUNT(*) n FROM jobs GROUP BY platform ORDER BY n DESC")},
            "by_location": {r["location"] or "unknown": r["n"] for r in conn.execute(
                """SELECT location, COUNT(*) n FROM jobs GROUP BY location
                   ORDER BY n DESC LIMIT 8""")},
        }
    finally:
        conn.close()


def missing_skill_counts(limit: int = 12) -> list[tuple[str, int]]:
    """Which skills keep coming up in jobs that the resume doesn't have.
    This is the most useful thing the database knows."""
    conn = connect()
    try:
        tally: dict[str, int] = {}
        for row in conn.execute("SELECT skills_missing FROM jobs"):
            try:
                for skill in json.loads(row[0] or "[]"):
                    tally[skill] = tally.get(skill, 0) + 1
            except json.JSONDecodeError:
                continue
        return sorted(tally.items(), key=lambda kv: -kv[1])[:limit]
    finally:
        conn.close()
