from models.job import Job


def deduplicate_jobs(jobs: list[Job]) -> list[Job]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[Job] = []
    for job in jobs:
        key = (job.company.casefold(), job.title.casefold(), job.location.casefold())
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique
