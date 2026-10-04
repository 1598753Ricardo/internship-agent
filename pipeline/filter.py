from dataclasses import replace
from datetime import date

from models.job import Job
from pipeline.normalize import normalize_city


def filter_jobs(jobs: list[Job], profile: dict, today: date | None = None) -> list[Job]:
    today = today or date.today()
    major = str(profile["education"]["major"]).casefold()
    locations = {
        normalize_city(city)
        for city in [*profile["location"]["preferred"], *profile["location"]["acceptable"]]
    }
    max_days = profile["availability"]["max_days_per_week"]
    remote_allowed = profile["location"]["remote_allowed"]
    accepted: list[Job] = []

    for job in jobs:
        if job.is_active is False:
            continue
        if job.deadline is not None and job.deadline < today:
            continue
        if job.required_majors and not any(
            required.casefold() in {major, f"{major}类"}
            for required in job.required_majors
        ):
            continue
        if job.location and job.location not in locations and (not remote_allowed or job.remote is False):
            continue

        risks = list(job.risk_reasons)
        if job.internship_days_per_week is not None and job.internship_days_per_week > max_days:
            risks.append(f"每周要求{job.internship_days_per_week}天，超过可投入的{max_days}天")
        if job.location and job.location not in locations and job.remote is True:
            risks.append("岗位所在地不在偏好城市，需确认远程安排")
        elif job.location and job.location not in locations and job.remote is None:
            risks.append("岗位异地且远程安排未明确，需核实")
        accepted.append(replace(job, risk_reasons=risks))

    return accepted
