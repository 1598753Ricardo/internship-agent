from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal


SourceType = Literal[
    "official_website", "official_wechat", "job_platform", "repost", "unknown"
]


@dataclass
class Job:
    id: str
    title: str
    company: str
    location: str
    remote: bool | None
    source: str
    source_url: str
    description: str
    requirements: list[str]
    education: str | None
    internship_days_per_week: int | None
    internship_duration: str | None
    deadline: date | str | None
    published_at: date | str | None
    collected_at: datetime | str | None
    refreshed_at: datetime | str | None = None
    source_job_id: str | None = None
    is_active: bool | None = None
    raw_text: str = ""
    source_type: SourceType = "unknown"
    direction: str | None = None
    required_majors: list[str] = field(default_factory=list)
    required_grades: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    business_tags: list[str] = field(default_factory=list)
    task_tags: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    unknown_fields: list[str] = field(default_factory=list)
    data_quality: list[str] = field(default_factory=list)
    mentor: str | None = None
    retention: str | None = None
    eligibility_score: int = 0
    direction_score: int = 0
    convenience_score: int = 0
    content_score: int = 0
    match_score: int = 0
    recommendation: str = ""
    match_reasons: list[str] = field(default_factory=list)
    risk_reasons: list[str] = field(default_factory=list)
