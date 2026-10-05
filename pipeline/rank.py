"""Transparent four-part scoring. Unknown facts receive neutral points, not claims."""

from dataclasses import replace
from datetime import date, datetime

from models.job import Job
from pipeline.normalize import normalize_city


CONTENT_GROUPS = (
    {"法律研究", "法律检索", "法规研究"},
    {"文书起草", "合同起草"},
    {"合同审查"},
    {"尽职调查"},
    {"仲裁", "诉讼", "案件支持"},
    {"英文法律工作"},
)
NEGATIVE_TASKS = {"纯行政", "纯文员", "扫描", "装订", "跑腿", "客服", "销售"}
FRESHNESS_ADJUSTMENTS = {"fresh": 0, "recent": 0, "stale": -3, "very_stale": -8, "unknown": -2}


def recommendation_for(score: int) -> str:
    if score >= 80:
        return "强烈推荐"
    if score >= 65:
        return "值得考虑"
    if score >= 50:
        return "一般"
    return "不推荐"


def score_job(job: Job, profile: dict, today: date | None = None) -> Job:
    today = today or date.today()
    reasons: list[str] = []
    risks = list(job.risk_reasons)
    education = profile["education"]
    skills = {item.casefold() for item in profile["skills"]}

    # Eligibility: major 8 + degree 8 + grade 6 + skills 8 = 30.
    eligibility = 0
    if job.required_majors:
        if any(item.casefold() in {education["major"].casefold(), f"{education['major'].casefold()}类"} for item in job.required_majors):
            eligibility += 8
            reasons.append("专业符合明确要求")
        else:
            risks.append("专业与明确要求不符")
    else:
        eligibility += 6

    degree = education["degree"]
    if not job.education:
        eligibility += 6
    elif job.education == "不限" or job.education == degree or job.education == f"{degree}及以上":
        eligibility += 8
        reasons.append("学历符合明确要求")
    elif job.education in {"硕士", "硕士及以上", "博士", "博士及以上"} and degree == "本科":
        risks.append(f"学历可能不符：岗位要求{job.education}")
    else:
        eligibility += 4
        risks.append(f"需人工核对学历要求：{job.education}")

    if not job.required_grades:
        eligibility += 4
    elif education["grade"] in job.required_grades:
        eligibility += 6
        reasons.append("年级符合明确要求")
    else:
        risks.append("年级与明确要求不符")

    if not job.required_skills:
        eligibility += 6
    else:
        matched = [item for item in job.required_skills if item.casefold() in skills]
        eligibility += round(8 * len(matched) / len(job.required_skills))
        if matched:
            reasons.append("具备明确要求的技能：" + "、".join(matched))
        missing = [item for item in job.required_skills if item.casefold() not in skills]
        if missing:
            risks.append("待确认技能：" + "、".join(missing))

    # Direction: take the strongest explicitly evidenced direction.
    directions = set(job.business_tags)
    if job.direction:
        directions.add(job.direction)
    aliases = {"商事诉讼": "商事争议"}
    directions = {aliases.get(item, item) for item in directions}
    high = directions & {aliases.get(item, item) for item in profile["preferred_directions"]["high"]}
    medium = directions & {aliases.get(item, item) for item in profile["preferred_directions"]["medium"]}
    if high:
        direction = 25
        reasons.append("高度偏好方向：" + "、".join(sorted(high)))
    elif medium:
        direction = 17
        reasons.append("可考虑方向：" + "、".join(sorted(medium)))
    elif directions:
        direction = 5
        risks.append("明确业务方向不在偏好列表中")
    else:
        direction = 12

    # Convenience: location 10 + schedule 15 = 25.
    preferred = {normalize_city(item) for item in profile["location"]["preferred"]}
    acceptable = {normalize_city(item) for item in profile["location"]["acceptable"]}
    if job.location in preferred:
        location_points = 10
        reasons.append(f"首选城市：{job.location}")
    elif job.location in acceptable:
        location_points = 7
        reasons.append(f"可接受城市：{job.location}")
    elif job.remote is True and profile["location"]["remote_allowed"]:
        location_points = 6
        reasons.append("明确支持远程，可跨城市")
    elif not job.location:
        location_points = 5
    else:
        location_points = 4

    days = job.internship_days_per_week
    preferred_days = profile["availability"]["preferred_days_per_week"]
    max_days = profile["availability"]["max_days_per_week"]
    if days is None:
        schedule_points = 10
    elif days <= preferred_days:
        schedule_points = 15
        reasons.append(f"每周{days}天，符合首选时间")
    elif days <= max_days:
        schedule_points = 12
        reasons.append(f"每周{days}天，在可投入范围内")
    else:
        schedule_points = 0
    convenience = 0 if days is not None and days > max_days else location_points + schedule_points

    # Each kind of legal work counts once, even when several synonyms are present.
    positive = sorted(set(job.task_tags) & set().union(*CONTENT_GROUPS))
    negative = sorted(set(job.task_tags) & NEGATIVE_TASKS)
    distinct_work = sum(bool(group & set(positive)) for group in CONTENT_GROUPS)
    content = min(20, 10 + 2 * distinct_work + (1 if "客户沟通" in job.task_tags else 0))
    avoid = set(profile["preferences"]["avoid"])
    for tag in negative:
        content -= 12 if tag in avoid or (tag == "销售" and "纯销售" in avoid) else 8
    content = max(0, content)
    if positive:
        reasons.append("明确工作内容：" + "、".join(positive))
    if negative:
        risks.append("包含需注意的任务：" + "、".join(negative))

    base = eligibility + direction + convenience + content
    if not isinstance(job.refreshed_at, datetime):
        freshness = "unknown"
    else:
        age = (today - job.refreshed_at.date()).days
        freshness = "fresh" if age <= 30 else "recent" if age <= 90 else "stale" if age <= 180 else "very_stale"
    adjustment = FRESHNESS_ADJUSTMENTS[freshness]
    total = max(0, min(100, base + adjustment))
    schedule_conflict = bool(days is not None and days > max_days and direction >= 17 and content >= 10)
    return replace(
        job, eligibility_score=eligibility, direction_score=direction,
        convenience_score=convenience, content_score=content,
        base_match_score=base, freshness_status=freshness,
        freshness_adjustment=adjustment, schedule_conflict=schedule_conflict,
        match_score=total, recommendation=recommendation_for(total),
        match_reasons=reasons, risk_reasons=risks,
    )


def rank_jobs(jobs: list[Job], profile: dict, today: date | None = None) -> list[Job]:
    return sorted(
        (score_job(job, profile, today=today) for job in jobs),
        key=lambda job: (-job.match_score, job.company, job.title),
    )
