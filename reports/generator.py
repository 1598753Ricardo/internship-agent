from datetime import datetime
from pathlib import Path

from models.job import Job


def generate_report(jobs: list[Job], collected_count: int, output_path: Path) -> Path:
    now = datetime.now().astimezone()
    recommended = sum(job.match_score >= 65 for job in jobs)
    lines = [
        "# 实习机会日报",
        "",
        f"生成时间：{now:%Y-%m-%d %H:%M %Z}",
        "",
        f"共抓取：{collected_count}",
        f"过滤后：{len(jobs)}",
        f"推荐：{recommended}",
        "",
    ]

    if not jobs:
        lines.extend(["暂无符合条件的岗位。", ""])

    for index, job in enumerate(sorted(jobs, key=lambda item: -item.match_score), start=1):
        lines.extend([
            f"## {index}. {job.company}｜{job.title}",
            "",
            f"匹配度：{job.match_score}/100",
            f"推荐：{job.recommendation}",
            "",
            f"地点：{job.location}" + ("（可远程）" if job.remote else ""),
            f"每周：{job.internship_days_per_week}天" if job.internship_days_per_week is not None else "每周：未注明",
            f"期限：{job.internship_duration or '未注明'}",
            f"截止日期：{job.deadline.isoformat() if job.deadline else '未注明'}",
            "",
            "匹配理由：",
        ])
        lines.extend(f"- {reason}" for reason in job.match_reasons)
        lines.extend(["", "注意事项："])
        lines.extend(f"- {reason}" for reason in job.risk_reasons or ["暂无明显注意事项"])
        lines.extend(["", "岗位链接：", job.source_url or "未提供", ""])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
