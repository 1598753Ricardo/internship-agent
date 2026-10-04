import re
from dataclasses import replace
from datetime import date, datetime
from urllib.parse import urlsplit, urlunsplit

from models.job import Job


CITY_ALIASES = {
    "广州市": "广州",
    "深圳市": "深圳",
    "东莞市": "东莞",
    "北京市": "北京",
    "天津市": "天津",
}


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_city(value: str | None) -> str:
    city = clean_text(value)
    return CITY_ALIASES.get(city, city)


def normalize_url(value: str | None) -> str:
    raw = clean_text(value)
    if not raw:
        return ""
    parts = urlsplit(raw)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise ValueError(f"Invalid job URL: {raw}")
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def normalize_date(value: date | str | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = clean_text(value)
    try:
        return date.fromisoformat(raw)
    except ValueError:
        try:
            return datetime.fromisoformat(raw).date()
        except ValueError:
            return datetime.strptime(raw, "%Y/%m/%d").date()


def normalize_datetime(value: datetime | str | None) -> datetime:
    if value is None or value == "":
        return datetime.now().astimezone()
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(clean_text(value))


def normalize_job(job: Job) -> Job:
    return replace(
        job,
        id=clean_text(job.id),
        title=clean_text(job.title),
        company=clean_text(job.company),
        location=normalize_city(job.location),
        source=clean_text(job.source),
        source_url=normalize_url(job.source_url),
        description=clean_text(job.description),
        requirements=[clean_text(item) for item in (job.requirements or []) if clean_text(item)],
        education=clean_text(job.education),
        internship_duration=clean_text(job.internship_duration),
        deadline=normalize_date(job.deadline),
        published_at=normalize_date(job.published_at),
        collected_at=normalize_datetime(job.collected_at),
        direction=clean_text(job.direction),
        required_majors=[clean_text(item) for item in (job.required_majors or []) if clean_text(item)],
        required_skills=[clean_text(item) for item in (job.required_skills or []) if clean_text(item)],
    )


def normalize_jobs(jobs: list[Job]) -> list[Job]:
    return [normalize_job(job) for job in jobs]
