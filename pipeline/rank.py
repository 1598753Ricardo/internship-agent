from dataclasses import replace

from models.job import Job
from pipeline.normalize import normalize_city


def recommendation_for(score: int) -> str:
    if score >= 80:
        return "强烈推荐"
    if score >= 65:
        return "值得考虑"
    if score >= 50:
        return "一般"
    return "不推荐"


def score_job(job: Job, profile: dict) -> Job:
    score = 0
    reasons: list[str] = []
    risks = list(job.risk_reasons)
    directions = set(profile["preferred_directions"])
    locations = {normalize_city(city) for city in profile["preferred_locations"]}
    skills = {skill.casefold() for skill in profile["skills"]}
    max_days = profile["availability"]["max_days_per_week"]

    if job.direction in directions:
        score += 35
        reasons.append(f"方向匹配：{job.direction}")
    else:
        risks.append("岗位方向不在偏好列表中")

    if job.location in locations:
        score += 20
        reasons.append(f"地点符合偏好：{job.location}")
    elif job.remote and profile["remote_allowed"]:
        score += 12
        reasons.append("支持远程实习")

    if job.remote and profile["remote_allowed"]:
        score += 5
        if job.location in locations:
            reasons.append("可远程安排")

    if job.internship_days_per_week is None:
        score += 5
        risks.append("每周到岗天数未明确")
    elif job.internship_days_per_week <= max_days:
        score += 15
        reasons.append(f"每周{job.internship_days_per_week}天，符合时间安排")
    else:
        score -= 10 * (job.internship_days_per_week - max_days)

    if job.required_skills:
        matched = [skill for skill in job.required_skills if skill.casefold() in skills]
        score += round(10 * len(matched) / len(job.required_skills))
        if matched:
            reasons.append("具备所需技能：" + "、".join(matched))
        missing = [skill for skill in job.required_skills if skill.casefold() not in skills]
        if missing:
            risks.append("待确认技能：" + "、".join(missing))
    else:
        score += 10
        reasons.append("无额外技能门槛")

    if job.education in {"", "不限", "本科", "本科及以上"}:
        score += 10
        reasons.append("学历要求符合当前阶段")
    else:
        risks.append(f"需确认学历要求：{job.education}")

    score = max(0, min(100, score))
    return replace(job, match_score=score, recommendation=recommendation_for(score), match_reasons=reasons, risk_reasons=risks)


def rank_jobs(jobs: list[Job], profile: dict) -> list[Job]:
    return sorted((score_job(job, profile) for job in jobs), key=lambda job: (-job.match_score, job.company, job.title))
