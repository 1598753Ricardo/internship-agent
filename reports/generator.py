from datetime import datetime
from pathlib import Path

from models.job import Job


def generate_report(jobs: list[Job], collected_count: int, output_path: Path) -> Path:
    now = datetime.now().astimezone()
    recommended = sum(job.match_score >= 65 for job in jobs)
    lines = [
        "# 实习机会日报", "",
        f"生成时间：{now:%Y-%m-%d %H:%M %Z}", "",
        f"共抓取：{collected_count}",
        f"过滤后：{len(jobs)}",
        f"推荐：{recommended}", "",
    ]
    if not jobs:
        lines.extend(["暂无符合条件的岗位。", ""])

    for index, job in enumerate(sorted(jobs, key=lambda item: -item.match_score), start=1):
        lines.extend([
            f"## {index}. {job.company}｜{job.title}", "",
            f"综合推荐：{job.match_score}/100（{job.recommendation}）",
            f"资格匹配：{job.eligibility_score}/30",
            f"方向匹配：{job.direction_score}/25",
            f"时间地点：{job.convenience_score}/25",
            f"岗位内容：{job.content_score}/20", "",
            "### 已知信息", "",
        ])
        known = [
            f"地点：{job.location}" if job.location else None,
            f"远程安排：{'支持' if job.remote else '不支持'}" if job.remote is not None else None,
            f"每周天数：{job.internship_days_per_week}天" if job.internship_days_per_week is not None else None,
            f"实习时长：{job.internship_duration}" if job.internship_duration else None,
            f"学历要求：{job.education}" if job.education else None,
            f"专业要求：{'、'.join(job.required_majors)}" if job.required_majors else None,
            f"年级要求：{'、'.join(job.required_grades)}" if job.required_grades else None,
            f"技能要求：{'、'.join(job.required_skills)}" if job.required_skills else None,
            f"截止日期：{job.deadline.isoformat()}" if job.deadline else None,
            f"导师安排：{job.mentor}" if job.mentor else None,
            f"留用机会：{job.retention}" if job.retention else None,
            f"业务标签：{'、'.join(job.business_tags)}" if job.business_tags else None,
            f"任务标签：{'、'.join(job.task_tags)}" if job.task_tags else None,
        ]
        lines.extend(f"- {item}" for item in known if item)
        lines.extend(["", "### 匹配理由", ""])
        lines.extend(f"- {item}" for item in job.match_reasons or ["尚无足够的明确匹配证据"])
        lines.extend(["", "### 问题", ""])
        lines.extend(f"- {item}" for item in [*job.risk_reasons, *job.data_quality] or ["暂无已识别问题"])
        lines.extend(["", "### 未知信息", ""])
        lines.extend(f"- {item}" for item in job.unknown_fields or ["无"])
        lines.extend(["", "### 岗位原文摘要", ""])
        summary = job.raw_text[:240] + ("…" if len(job.raw_text) > 240 else "") if job.raw_text else "未提供岗位原文"
        lines.extend([summary, "", "### 原文证据", ""])
        lines.extend(f"- {item}" for item in job.evidence or ["暂无可提取的标签证据"])
        lines.extend([
            "", "### 岗位链接", "", job.source_url or "未提供有效链接", "",
            "### 信息来源", "", f"{job.source or '未知'}（{job.source_type}）", "",
        ])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
