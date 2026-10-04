from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class Job:
    id: str
    title: str
    company: str
    location: str
    remote: bool
    source: str
    source_url: str
    description: str
    requirements: list[str]
    education: str
    internship_days_per_week: int | None
    internship_duration: str
    deadline: date | str | None
    published_at: date | str | None
    collected_at: datetime | str | None
    direction: str = ""
    required_majors: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    match_score: int = 0
    recommendation: str = ""
    match_reasons: list[str] = field(default_factory=list)
    risk_reasons: list[str] = field(default_factory=list)
