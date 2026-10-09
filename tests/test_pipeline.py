from dataclasses import replace
from datetime import date
from pathlib import Path

import yaml

from collectors.mock_collector import MockCollector
from main import print_field_coverage
from pipeline.deduplicate import deduplicate_jobs
from pipeline.filter import filter_jobs
from pipeline.normalize import normalize_jobs
from pipeline.rank import rank_jobs, score_job
from reports.generator import generate_report


def profile() -> dict:
    with open("config/profile.example.yaml", encoding="utf-8") as file:
        return yaml.safe_load(file)


def jobs():
    return deduplicate_jobs(normalize_jobs(MockCollector().collect()))


def test_expired_job_is_filtered():
    assert "expired" not in {job.id for job in filter_jobs(jobs(), profile())}


def test_explicit_major_mismatch_is_filtered():
    assert "unrelated" not in {job.id for job in filter_jobs(jobs(), profile())}


def test_hard_reject_reason_counts():
    counts = {}
    accepted = filter_jobs(jobs(), profile(), today=date.today(), rejection_counts=counts)
    assert counts["expired"] >= 1
    assert counts["major_mismatch"] >= 1
    assert sum(counts.values()) + len(accepted) == len(jobs())


def test_field_coverage_counts_unknown_boolean_as_missing(capsys):
    original = jobs()[0]
    print_field_coverage([replace(original, remote=True), replace(original, remote=None)])
    assert "[field coverage] remote: 1/2 (50.0%)" in capsys.readouterr().out


def test_similar_spelling_does_not_count_as_same_major():
    original = MockCollector().collect()[0]
    raw = original.raw_text.replace("法学专业", "非法学专业")
    job = normalize_jobs([replace(original, raw_text=raw, required_majors=["非法学"])])[0]
    assert filter_jobs([job], profile()) == []


def test_unknown_weekly_days_are_preserved():
    accepted = {job.id: job for job in filter_jobs(jobs(), profile())}
    assert accepted["unknown-days"].internship_days_per_week is None
    assert "每周天数" in accepted["unknown-days"].unknown_fields


def test_remote_job_can_cross_city():
    accepted = {job.id for job in filter_jobs(jobs(), profile())}
    assert "remote-law" in accepted
    assert "wrong-city" not in accepted


def test_onsite_wording_does_not_prove_remote_is_forbidden():
    original = MockCollector().collect()[0]
    raw = original.raw_text.replace("不支持远程，", "")
    job = normalize_jobs([replace(original, raw_text=raw)])[0]
    assert job.remote is None
    assert "远程安排" in job.unknown_fields


def test_five_day_job_loses_at_least_fifteen_points():
    five = next(job for job in jobs() if job.id == "five-days")
    two_day_raw = five.raw_text.replace("每周5天", "每周2天")
    two = normalize_jobs([replace(five, raw_text=two_day_raw, internship_days_per_week=2)])[0]
    five_score = score_job(five, profile())
    two_score = score_job(two, profile())
    assert two_score.match_score - five_score.match_score >= 15
    assert five_score.convenience_score == 0
    assert five_score.recommendation == "一般"
    assert any("超过" in issue for issue in filter_jobs([five], profile())[0].risk_reasons)


def test_same_company_title_and_city_are_deduplicated():
    normalized = normalize_jobs(MockCollector().collect())
    assert len(normalized) == 11
    unique = deduplicate_jobs(normalized)
    assert len(unique) == 10
    assert "foreign-law-copy" not in {job.id for job in unique}


def test_invalid_url_keeps_other_jobs_and_marks_quality(capsys):
    original = MockCollector().collect()
    bad = replace(original[1], source_url="not a valid URL")
    normalized = normalize_jobs([original[0], bad])
    assert len(normalized) == 2
    assert normalized[1].source_url == ""
    assert "有效岗位链接" in normalized[1].unknown_fields
    assert any("岗位链接无效" in issue for issue in normalized[1].data_quality)
    assert "warning" in capsys.readouterr().err


def test_invalid_date_is_unknown_and_does_not_stop_batch(capsys):
    original = MockCollector().collect()
    bad = replace(original[1], deadline="2026-02-30", raw_text=original[1].raw_text + "截止日期：2026-02-30。")
    normalized = normalize_jobs([original[0], bad])
    assert len(normalized) == 2
    assert normalized[1].deadline is None
    assert "截止日期" in normalized[1].unknown_fields
    assert any("无法解析" in issue for issue in normalized[1].data_quality)
    assert "warning" in capsys.readouterr().err


def test_missing_original_text_is_skipped_with_warning(capsys):
    original = MockCollector().collect()
    normalized = normalize_jobs([original[0], replace(original[1], raw_text="")])
    assert len(normalized) == 1
    assert "warning" in capsys.readouterr().err


def test_tags_and_evidence_must_be_in_original_text():
    original = MockCollector().collect()[0]
    normalized = normalize_jobs([replace(original, business_tags=["不存在的业务"], task_tags=["销售"], evidence=["导师很好"])])[0]
    assert "不存在的业务" not in normalized.business_tags
    assert "销售" not in normalized.task_tags
    assert "导师很好" not in normalized.evidence
    assert normalized.business_tags and normalized.task_tags
    assert all(snippet in normalized.raw_text for snippet in normalized.evidence)


def test_report_contains_four_scores_and_unknowns():
    ranked = rank_jobs(filter_jobs(jobs(), profile(), today=date.today()), profile())
    path = Path("data/test_daily_report.md")
    try:
        report = generate_report(ranked, 11, path).read_text(encoding="utf-8")
    finally:
        path.unlink(missing_ok=True)
    assert [job.match_score for job in ranked] == sorted((job.match_score for job in ranked), reverse=True)
    for heading in ("综合推荐", "资格匹配", "方向匹配", "时间地点", "岗位内容", "已知信息", "匹配理由", "问题", "未知信息", "岗位原文摘要", "岗位链接", "信息来源"):
        assert heading in report
    assert "导师安排" in report
    assert "导师很好" not in report
