import re
import sys
from dataclasses import replace
from datetime import date, datetime
from urllib.parse import urlsplit, urlunsplit

from models.job import Job
from pipeline.evidence import extract_tags


CITY_ALIASES = {
    "广州市": "广州", "深圳市": "深圳", "东莞市": "东莞",
    "北京市": "北京", "天津市": "天津",
}
SOURCE_TYPES = {"official_website", "official_wechat", "job_platform", "repost", "unknown"}


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def clean_multiline_text(value: str | None) -> str:
    return "\n".join(line for raw_line in (value or "").splitlines() if (line := clean_text(raw_line)))


def normalize_city(value: str | None) -> str:
    city = clean_text(value)
    return CITY_ALIASES.get(city, city)


def normalize_url(value: str | None) -> str:
    raw = clean_text(value)
    if not raw:
        return ""
    parts = urlsplit(raw)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname or re.search(r"\s", parts.netloc):
        raise ValueError(f"invalid URL: {raw}")
    _ = parts.port  # Reject malformed ports while retaining the original URL in data_quality.
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


def normalize_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(clean_text(value))


def normalize_job(job: Job) -> Job:
    title, company = clean_text(job.title), clean_text(job.company)
    if not clean_text(job.id) or not title or not company:
        raise ValueError("missing id, title, or company")

    raw_text = clean_multiline_text(job.raw_text)
    quality = list(job.data_quality)
    if not raw_text:
        raise ValueError("missing raw_text; cannot verify job facts")
    if title not in raw_text or company not in raw_text:
        raise ValueError("title or company lacks raw_text support")

    def supported(value: str | None, field_name: str) -> str | None:
        cleaned = clean_text(value)
        if cleaned and cleaned not in raw_text:
            quality.append(f"{field_name}缺少原文依据：{cleaned}")
            return None
        return cleaned or None

    def supported_list(values: list[str] | None, field_name: str) -> list[str]:
        return [found for value in (values or []) if (found := supported(value, field_name))]

    location = normalize_city(job.location)
    if location and location not in raw_text:
        quality.append(f"地点缺少原文依据：{location}")
        location = ""

    remote = job.remote
    remote_denied = any(term in raw_text for term in ("不支持远程", "不可远程", "无法远程"))
    remote_supported = bool(re.search(r"(?<!不)支持远程|(?<!不)可远程|远程办公|远程实习", raw_text))
    if remote is True and (remote_denied or not remote_supported):
        quality.append("远程安排缺少原文依据")
        remote = None
    elif remote is False and not remote_denied:
        quality.append("非远程安排缺少原文依据")
        remote = None

    days = job.internship_days_per_week
    day_supported = days is not None and bool(re.search(
        rf"每周\D{{0,5}}{days}\s*天|{days}\s*天\s*[／/]\s*周", raw_text
    ))
    if days is not None and not day_supported:
        quality.append(f"每周天数缺少原文依据：{days}")
        days = None

    is_active = job.is_active
    if is_active is False and not any(mark in raw_text for mark in ("当前职位已下线", "该职位已下线", "职位已下线")):
        quality.append("下线状态缺少原文依据")
        is_active = None
    elif is_active is True and not any(mark in raw_text for mark in ("投个简历", "立即投递", "投递简历", "申请职位")):
        quality.append("可投递状态缺少原文依据")
        is_active = None

    def safe_date(value: date | str | None, field_name: str) -> date | None:
        if value is None or value == "":
            return None
        original = value.isoformat() if isinstance(value, date) else clean_text(value)
        if original not in raw_text:
            quality.append(f"{field_name}缺少原文依据：{original}")
            return None
        try:
            return normalize_date(value)
        except (ValueError, TypeError):
            quality.append(f"{field_name}无法解析：{original}")
            return None

    try:
        source_url = normalize_url(job.source_url)
    except (ValueError, TypeError) as exc:
        quality.append(f"岗位链接无效：{exc}")
        source_url = ""

    try:
        collected_at = normalize_datetime(job.collected_at)
    except (ValueError, TypeError):
        quality.append("采集时间无法解析")
        collected_at = None

    source_type = job.source_type
    if source_type not in SOURCE_TYPES:
        quality.append(f"信息来源类型无效：{source_type}")
        source_type = "unknown"

    business_tags, task_tags, tag_evidence = extract_tags(raw_text)
    unsupported_tags = (set(job.business_tags) - set(business_tags)) | (set(job.task_tags) - set(task_tags))
    if unsupported_tags:
        quality.append("无原文依据的标签已移除：" + "、".join(sorted(unsupported_tags)))
    direction = supported(job.direction, "岗位方向")

    supplied_evidence = [item for item in job.evidence if item and item in raw_text]
    if len(supplied_evidence) != len(job.evidence):
        quality.append("无原文依据的证据片段已移除")

    result = replace(
        job,
        id=clean_text(job.id), title=title, company=company, location=location,
        remote=remote, source=clean_text(job.source), source_url=source_url,
        raw_text=raw_text, description=raw_text, requirements=supported_list(job.requirements, "要求"),
        education=supported(job.education, "学历要求"),
        required_majors=supported_list(job.required_majors, "专业要求"),
        required_grades=supported_list(job.required_grades, "年级要求"),
        required_skills=supported_list(job.required_skills, "技能要求"),
        internship_days_per_week=days,
        internship_duration=supported(job.internship_duration, "实习时长"),
        deadline=safe_date(job.deadline, "截止日期"),
        published_at=safe_date(job.published_at, "发布日期"),
        collected_at=collected_at, source_type=source_type, direction=direction,
        is_active=is_active,
        business_tags=business_tags, task_tags=task_tags,
        evidence=list(dict.fromkeys([*supplied_evidence, *tag_evidence])),
        mentor=supported(job.mentor, "导师安排"), retention=supported(job.retention, "留用机会"),
        data_quality=quality,
    )

    unknown_fields = [
        label for label, missing in (
            ("地点", not result.location), ("远程安排", result.remote is None),
            ("专业要求", not result.required_majors), ("学历要求", not result.education),
            ("年级要求", not result.required_grades), ("技能要求", not result.required_skills),
            ("每周天数", result.internship_days_per_week is None),
            ("实习时长", result.internship_duration is None),
            ("截止日期", result.deadline is None), ("发布日期", result.published_at is None),
            ("导师安排", result.mentor is None), ("留用机会", result.retention is None),
            ("业务方向", not result.business_tags and not result.direction),
            ("岗位任务", not result.task_tags),
            ("信息来源类型", result.source_type == "unknown"),
            ("岗位状态", result.is_active is None),
            ("岗位原文", not result.raw_text), ("有效岗位链接", not result.source_url),
        ) if missing
    ]
    return replace(result, unknown_fields=unknown_fields)


def normalize_jobs(jobs: list[Job]) -> list[Job]:
    normalized: list[Job] = []
    for job in jobs:
        try:
            result = normalize_job(job)
        except Exception as exc:
            print(f"[normalize] warning: skipped {job.id}: {exc}", file=sys.stderr)
            continue
        for issue in result.data_quality[len(job.data_quality):]:
            print(f"[normalize] warning: {job.id}: {issue}", file=sys.stderr)
        normalized.append(result)
    return normalized
