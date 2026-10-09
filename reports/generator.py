"""Daily discovery report with evidence and explicit uncertainty."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from models.job import Job


def _job_lines(job: Job, index: int) -> list[str]:
    lines = [
        f"### {index}. {job.company}｜{job.title}", "",
        f"综合推荐：{job.match_score}/100（{job.recommendation}）",
        f"基础匹配：{job.base_match_score}/100；时效调整：{job.freshness_adjustment:+d}",
        f"资格匹配：{job.eligibility_score}/30",
        f"方向匹配：{job.direction_score}/25",
        f"时间地点：{job.convenience_score}/25",
        f"岗位内容：{job.content_score}/20",
        f"时效状态：{job.freshness_status}",
        f"发现状态：{job.discovery_status}", "",
    ]
    if job.schedule_conflict:
        lines.extend(["**机会本身值得看，但与你当前可投入时间冲突。**", ""])
    if job.changes:
        lines.extend(["变化内容：", *(f"- {item}" for item in job.changes), ""])
    lines.extend(["#### 已知信息", ""])
    known = [
        f"岗位状态：{'可投递' if job.is_active else '已下线'}" if job.is_active is not None else None,
        f"地点：{job.location}" if job.location else None,
        f"远程安排：{'支持' if job.remote else '不支持'}" if job.remote is not None else None,
        f"每周天数：{job.internship_days_per_week}天" if job.internship_days_per_week is not None else None,
        f"实习时长：{job.internship_duration}" if job.internship_duration else None,
        f"学历要求：{job.education}" if job.education else None,
        f"专业要求：{'、'.join(job.required_majors)}" if job.required_majors else None,
        f"年级要求：{'、'.join(job.required_grades)}" if job.required_grades else None,
        f"技能要求：{'、'.join(job.required_skills)}" if job.required_skills else None,
        f"截止日期：{job.deadline.isoformat()}" if job.deadline else None,
        f"页面刷新时间：{job.refreshed_at:%Y-%m-%d}" if job.refreshed_at else None,
        f"导师安排：{job.mentor}" if job.mentor else None,
        f"留用机会：{job.retention}" if job.retention else None,
        f"业务标签：{'、'.join(job.business_tags)}" if job.business_tags else None,
        f"任务标签：{'、'.join(job.task_tags)}" if job.task_tags else None,
    ]
    lines.extend(f"- {item}" for item in known if item)
    lines.extend(["", "#### 匹配理由", ""])
    lines.extend(f"- {item}" for item in job.match_reasons or ["尚无足够的明确匹配证据"])
    lines.extend(["", "#### 问题", ""])
    lines.extend(f"- {item}" for item in [*job.risk_reasons, *job.data_quality] or ["暂无已识别问题"])
    lines.extend(["", "#### 未知信息", ""])
    lines.extend(f"- {item}" for item in job.unknown_fields or ["无"])
    lines.extend(["", "#### 岗位原文摘要", ""])
    summary = job.raw_text[:240] + ("…" if len(job.raw_text) > 240 else "") if job.raw_text else "未提供岗位原文"
    lines.extend([summary, "", "#### 原文证据", ""])
    lines.extend(f"- {item}" for item in job.evidence or ["暂无可提取的标签证据"])
    lines.extend([
        "", "#### 岗位链接", "", job.source_url or "未提供有效链接", "",
        "#### 信息来源", "", f"{job.source or '未知'}（{job.source_type}）", "",
    ])
    return lines


def generate_report(
    jobs: list[Job], collected_count: int, output_path: Path,
    updated_jobs: list[Job] | None = None, tracked_total: int | None = None,
    collection_status: str = "success",
) -> Path:
    now = datetime.now(timezone(timedelta(hours=8)))
    ordered = sorted(jobs, key=lambda item: (-item.match_score, item.company, item.title))
    new = [job for job in ordered if job.discovery_status == "new"]
    updated = sorted(
        updated_jobs if updated_jobs is not None else [job for job in ordered if job.discovery_status == "updated"],
        key=lambda item: (-item.match_score, item.company, item.title),
    )
    updated = [job for job in updated if job.discovery_status == "updated"]
    top = [job for job in ordered if job.is_active is True][:5]
    conflicts = [job for job in ordered if job.schedule_conflict][:5]
    recommended = sum(job.match_score >= 65 for job in jobs)
    lines = [
        "# 今日实习机会", "",
        f"生成时间：{now:%Y-%m-%d %H:%M %Z}", "",
        f"采集状态：{collection_status}",
        f"共抓取：{collected_count}", f"过滤后：{len(jobs)}", f"推荐：{recommended}", "",
    ]
    if collection_status in {"blocked", "failed"}:
        lines.extend(["**今日采集失败或被限制，不能判断是否有新岗位。**", ""])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path
    if collection_status == "partial":
        lines.extend(["**部分岗位采集失败，以下结果可能不完整。**", ""])
    uncertain = collection_status == "partial"
    sections = (
        ("今日新发现", new, "本次采集不完整，无法判断是否有新岗位。" if uncertain else "今天没有新发现的符合条件岗位。"),
        ("岗位发生变化", updated, "本次采集不完整，无法判断是否有岗位变化。" if uncertain else "今天没有检测到岗位变化。"),
        ("今日最值得看", top, "暂无明确可投递的岗位。"),
        ("时间不合适但值得关注", conflicts, "暂无符合这一条件的岗位。"),
    )
    for heading, section_jobs, empty in sections:
        lines.extend([f"## {heading}", ""])
        if section_jobs:
            for index, job in enumerate(section_jobs, 1):
                lines.extend(_job_lines(job, index))
        else:
            lines.extend([empty, ""])
    lines.extend(["## 已见岗位", "", f"已跟踪 {tracked_total if tracked_total is not None else len(jobs)} 个岗位。", ""])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
