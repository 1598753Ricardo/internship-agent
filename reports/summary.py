"""Compact machine and GitHub summaries of one run."""

import json
from datetime import date
from pathlib import Path

from models.job import Job


VALID_STATUSES = {"success", "partial", "blocked", "failed"}


def collection_status(
    *, blocked_reason: str | None = None, detail_failures: int = 0,
    search_failures: int = 0, collected: int = 0, normalized: int | None = None,
    unexpected_error: bool = False,
) -> str:
    if blocked_reason:
        return "blocked"
    if unexpected_error:
        return "failed"
    incomplete = detail_failures > 0 or search_failures > 0 or (normalized is not None and normalized < collected)
    if incomplete:
        return "partial" if (normalized if normalized is not None else collected) > 0 else "failed"
    return "success"


def _brief(job: Job) -> dict:
    return {
        "company": job.company,
        "title": job.title,
        "score": job.match_score,
        "url": job.source_url,
        "discovery_status": job.discovery_status,
        "location": job.location or None,
        "days_per_week": job.internship_days_per_week,
        "changes": list(job.changes),
    }


def build_run_summary(
    *, status: str, collected: int, accepted: list[Job],
    detail: str | None = None,
) -> dict:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid collection status: {status}")
    ordered = sorted(accepted, key=lambda job: (-job.match_score, job.company, job.title))
    grouped = {name: [job for job in ordered if job.discovery_status == name] for name in ("new", "updated", "seen")}
    conflicts = [job for job in ordered if job.schedule_conflict]
    top = [job for job in ordered if job.is_active is True][:5]
    return {
        "collection_status": status,
        "collection_detail": detail or "",
        "collected": collected,
        "accepted": len(accepted),
        "new": len(grouped["new"]),
        "updated": len(grouped["updated"]),
        "seen": len(grouped["seen"]),
        "schedule_conflict": len(conflicts),
        "new_jobs": [_brief(job) for job in grouped["new"][:5]],
        "updated_jobs": [_brief(job) for job in grouped["updated"][:5]],
        "top_jobs": [_brief(job) for job in top],
        "schedule_conflict_jobs": [_brief(job) for job in conflicts[:5]],
    }


def write_run_summary(path: Path, summary: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def should_notify(summary: dict) -> bool:
    return summary.get("collection_status") in {"success", "partial"} and (
        summary.get("new", 0) > 0 or summary.get("updated", 0) > 0
    )


def _plain(value) -> str:
    """Keep untrusted job text on one line and avoid GitHub mentions."""
    return " ".join(str(value or "").split()).replace("@", "@\u200b").replace("<", "&lt;").replace(">", "&gt;")


def _job_list(items: list[dict]) -> list[str]:
    lines = []
    for index, job in enumerate(items, 1):
        place = _plain(job.get("location")) or "地点未知"
        days = job.get("days_per_week")
        schedule = f"{days}天/周" if days is not None else "每周天数未知"
        lines.extend([
            f"{index}. {_plain(job.get('company'))}｜{_plain(job.get('title'))} — {job.get('score', 0)}分",
            f"   {place}｜{schedule}",
            f"   {job.get('url') or '岗位链接未知'}",
        ])
        for change in job.get("changes", []):
            lines.append(f"   - {_plain(change)}")
    return lines


def render_actions_summary(summary: dict) -> str:
    status = summary["collection_status"]
    lines = ["# Internship Agent 每日运行", "", f"采集状态：**{status}**", ""]
    if status in {"blocked", "failed"}:
        lines.extend(["**今日采集失败或被限制，无法判断是否有新岗位。**", ""])
    elif status == "partial":
        lines.extend(["**部分岗位采集失败，以下结果可能不完整。**", ""])
    if summary.get("collection_detail"):
        lines.extend([f"原因：{_plain(summary['collection_detail'])}", ""])
    uncertain = status in {"blocked", "failed"}
    lines.extend([
        f"- 抓取岗位数：{summary['collected']}",
        f"- 有效岗位数：{summary['accepted']}",
        f"- 新岗位：{'未统计' if uncertain else summary['new']}",
        f"- 更新岗位：{'未统计' if uncertain else summary['updated']}",
        f"- 已见岗位：{'未统计' if uncertain else summary['seen']}",
        f"- 时间冲突岗位：{'未统计' if uncertain else summary['schedule_conflict']}", "",
    ])
    for title, key in (
        ("今日新岗位", "new_jobs"), ("Top 5", "top_jobs"),
        ("时间冲突但值得关注", "schedule_conflict_jobs"),
    ):
        lines.extend([f"## {title}", ""])
        if status in {"blocked", "failed"}:
            lines.extend(["采集未完成，暂无可靠结果。", ""])
        else:
            lines.extend(_job_list(summary.get(key, [])) or (["本次采集不完整，暂无可靠结论。"] if status == "partial" else ["无"]))
            lines.append("")
    return "\n".join(lines)


def build_issue_comment(summary: dict, today: date) -> str:
    if not should_notify(summary):
        return ""
    lines = [
        f"## {today.isoformat()} 实习更新", "",
        f"新岗位：{summary['new']}", f"更新岗位：{summary['updated']}", "",
    ]
    if summary["collection_status"] == "partial":
        lines.extend(["部分采集失败，结果可能不完整。", ""])
    for title, key, count_key in (
        ("新岗位", "new_jobs", "new"), ("更新岗位", "updated_jobs", "updated"),
    ):
        if summary[count_key] == 0:
            continue
        lines.extend([f"### {title}", ""])
        lines.extend(_job_list(summary.get(key, [])))
        remaining = summary[count_key] - len(summary.get(key, []))
        if remaining > 0:
            lines.append(f"另有 {remaining} 个岗位，详见本次 Actions Artifact。")
        lines.append("")
    return "\n".join(lines)
