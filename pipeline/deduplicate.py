from models.job import Job
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def canonical_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    path = parts.path.rstrip("/") or "/"
    if host in {"shixiseng.com", "www.shixiseng.com"} and path.startswith("/intern/inn_"):
        return f"https://www.shixiseng.com{path}"
    query = urlencode([
        (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() != "pcm" and not key.lower().startswith("utm_")
    ])
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def deduplicate_jobs(jobs: list[Job]) -> list[Job]:
    seen_source_ids: set[tuple[str, str]] = set()
    seen_urls: set[str] = set()
    seen_descriptions: set[tuple[str, str, str]] = set()
    unique: list[Job] = []
    for job in jobs:
        source_id = (job.source.casefold(), job.source_job_id.casefold()) if job.source_job_id else None
        url = canonical_url(job.source_url)
        description = (job.company.casefold(), job.title.casefold(), job.location.casefold())
        if (source_id and source_id in seen_source_ids) or (url and url in seen_urls) or description in seen_descriptions:
            continue
        if source_id:
            seen_source_ids.add(source_id)
        if url:
            seen_urls.add(url)
        seen_descriptions.add(description)
        unique.append(job)
    return unique
