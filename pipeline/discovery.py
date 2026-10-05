"""Small local record of jobs seen across runs."""

import hashlib
import json
import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from models.job import Job


TRACKED_FIELDS = {
    "deadline": "deadline",
    "days_per_week": "internship_days_per_week",
    "duration": "internship_duration",
    "education": "education",
    "is_active": "is_active",
    "remote": "remote",
}
REFRESH_LINE = re.compile(r"^\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}:\d{2})? 刷新$")


def job_key(job: Job) -> str:
    if job.source_job_id:
        return f"{job.source}:{job.source_job_id}"
    parts = urlsplit(job.source_url)
    canonical = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))
    if not canonical:
        raise ValueError(f"job {job.id} has no stable source ID or URL")
    return f"{job.source}:url:{canonical}"


def _stable_text(job: Job) -> str:
    return "\n".join(line for line in job.raw_text.splitlines() if not REFRESH_LINE.fullmatch(line.strip()))


def _snapshot(job: Job) -> dict:
    values = {}
    for name, attr in TRACKED_FIELDS.items():
        value = getattr(job, attr)
        values[name] = value.isoformat() if hasattr(value, "isoformat") else value
    return values


def content_hash(job: Job) -> str:
    fields = {
        "title": job.title, "company": job.company, "location": job.location,
        "remote": job.remote, "education": job.education,
        "days": job.internship_days_per_week, "duration": job.internship_duration,
        "deadline": job.deadline.isoformat() if hasattr(job.deadline, "isoformat") else job.deadline,
        "raw_text": _stable_text(job), "is_active": job.is_active,
    }
    payload = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "jobs": {}}
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("jobs"), dict):
        raise ValueError(f"invalid state file: {path}")
    return state


def classify_jobs(jobs: list[Job], state: dict, now: datetime) -> tuple[list[Job], dict]:
    previous = state["jobs"]
    entries = dict(previous)
    classified = []
    timestamp = now.isoformat()
    for job in jobs:
        key = job_key(job)
        old = previous.get(key)
        digest = content_hash(job)
        snapshot = _snapshot(job)
        if old is None:
            status, changes, first_seen = "new", [], timestamp
        elif old.get("last_content_hash") == digest:
            status, changes, first_seen = "seen", [], old["first_seen_at"]
        else:
            status, first_seen = "updated", old["first_seen_at"]
            old_snapshot = old.get("snapshot", {})
            changes = [
                f"{field}: {_display(old_snapshot.get(field))} → {_display(value)}"
                for field, value in snapshot.items() if old_snapshot.get(field) != value
            ]
            if not changes:
                changes = ["招聘正文或基本信息已更新"]
        entries[key] = {
            "source": job.source, "source_job_id": job.source_job_id,
            "source_url": job.source_url, "first_seen_at": first_seen,
            "last_seen_at": timestamp, "last_content_hash": digest,
            "last_match_score": job.match_score, "snapshot": snapshot,
        }
        classified.append(replace(job, discovery_status=status, changes=changes))
    return classified, {"version": 1, "jobs": entries}


def _display(value) -> str:
    if value is None:
        return "未知"
    if value is True:
        return "是"
    if value is False:
        return "否"
    return str(value)


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
