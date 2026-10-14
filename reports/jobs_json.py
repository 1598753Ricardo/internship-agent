"""Export scored Job records for a frontend without changing their ranking."""

import json
from datetime import date
from pathlib import Path

from models.job import Job


def write_jobs_json(path: Path, jobs: list[Job]) -> Path:
    records = [
        {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "remote": job.remote,
            "match_score": job.match_score,
            "recommendation": job.recommendation,
            "match_reasons": job.match_reasons,
            "risk_reasons": job.risk_reasons,
            "requirements": job.requirements,
            "deadline": job.deadline.isoformat() if isinstance(job.deadline, date) else job.deadline or "",
            "source_url": job.source_url,
            "business_tags": job.business_tags,
            "task_tags": job.task_tags,
        }
        for job in jobs
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
