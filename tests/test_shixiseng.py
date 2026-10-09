from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest
import yaml

import collectors.shixiseng as shixiseng
from collectors.shixiseng import ShixisengCollector, canonical_detail_url, discover_detail_urls, parse_detail
from pipeline.deduplicate import deduplicate_jobs
from pipeline.filter import filter_jobs
from pipeline.normalize import normalize_jobs


FIXTURES = Path(__file__).parent / "fixtures"


def profile() -> dict:
    return yaml.safe_load(Path("config/profile.example.yaml").read_text(encoding="utf-8"))


def html(name: str) -> str:
    return (FIXTURES / f"shixiseng_{name}.html").read_text(encoding="utf-8")


def url(job_id: str) -> str:
    return f"https://www.shixiseng.com/intern/inn_{job_id}"


def test_normal_bachelor_legal_posting_uses_detail_evidence():
    job = normalize_jobs([parse_detail(html("normal"), url("normal123"))])[0]
    assert job.title == "法务实习生" and job.company == "测试公司甲"
    assert job.location == "广州" and job.education == "本科"
    assert job.internship_days_per_week == 2 and job.internship_duration == "3个月"
    assert job.required_majors == ["法学"] and job.required_grades == ["大三", "大四"]
    assert job.required_skills == ["CET-6"] and job.is_active is True
    assert job.deadline.isoformat() == "2026-12-31"
    assert job.published_at is None  # The page's date is labelled "refreshed".
    assert job.refreshed_at == datetime(2026, 10, 5)
    assert job.source == "shixiseng" and job.source_type == "job_platform"
    assert "职位百科" not in job.raw_text and "导师很好" not in job.raw_text
    assert "相关推荐" not in job.raw_text


def test_five_day_posting_is_read_from_detail_page():
    job = normalize_jobs([parse_detail(html("five_days"), url("five123"))])[0]
    assert job.internship_days_per_week == 5
    assert any("超过" in issue for issue in filter_jobs([job], profile())[0].risk_reasons)


def test_offline_job_is_hard_rejected():
    job = normalize_jobs([parse_detail(html("offline"), url("offline123"))])[0]
    assert job.is_active is False
    assert filter_jobs([job], profile()) == []


def test_master_education_does_not_turn_preference_into_major_requirement():
    job = normalize_jobs([parse_detail(html("master"), url("master123"))])[0]
    assert job.education == "硕士"
    assert job.required_majors == []


def test_missing_fields_stay_unknown():
    job = normalize_jobs([parse_detail(html("missing"), url("missing123"))])[0]
    assert job.location == ""
    assert job.remote is None and job.internship_days_per_week is None
    assert job.internship_duration is None and job.deadline is None
    assert job.education is None and job.is_active is None
    assert "每周天数" in job.unknown_fields and "岗位状态" in job.unknown_fields


def test_obfuscated_detail_day_glyph_is_not_guessed():
    page = html("normal").replace("2天／周", "\ue123天／周")
    job = normalize_jobs([parse_detail(page, url("glyph123"))])[0]
    assert job.internship_days_per_week is None
    assert "每周天数" in job.unknown_fields


def test_complex_education_phrase_remains_unknown():
    page = html("missing").replace("相关专业优先", "本科大四保研或研究生在读")
    job = normalize_jobs([parse_detail(page, url("complex123"))])[0]
    assert job.education is None


def test_detail_url_is_canonical_and_cross_domain_url_is_ignored():
    canonical = canonical_detail_url(url("normal123") + "?pcm=pc_SearchList&utm_source=test")
    assert canonical == (url("normal123"), "inn_normal123")
    assert canonical_detail_url("https://evil.example/intern/inn_normal123") is None


def test_duplicate_search_discovery_and_source_id_deduplication():
    page = f'<a href="{url("same123")}?pcm=pc_SearchList">first</a><a href="/intern/inn_same123?pcm=other">again</a>'
    assert discover_detail_urls(page) == [url("same123")]
    first = parse_detail(html("normal"), url("same123"))
    second = replace(first, title="不同标题", company="不同公司", source_url=url("same123") + "?pcm=pc_SearchList")
    assert len(deduplicate_jobs([first, second])) == 1


def test_one_parse_failure_does_not_stop_later_job(monkeypatch, capsys):
    monkeypatch.setattr(shixiseng, "KEYWORDS", ("法务", "合规"))
    monkeypatch.setattr(shixiseng, "CITIES", ("广州",))
    monkeypatch.setattr(shixiseng.time, "sleep", lambda _: None)
    search = f'<a href="{url("bad123")}">bad 5天/周</a><a href="{url("good123")}">good 5天/周</a>'

    class FakeHttp:
        def get(self, requested, **kwargs):
            content = search if requested == shixiseng.SEARCH_URL else html("broken") if requested == url("bad123") else html("normal")
            return type("Response", (), {"status_code": 200, "content": content.encode("utf-8")})()

    collector = ShixisengCollector(max_jobs=10, http=FakeHttp())
    jobs = collector.collect()
    assert collector.stats == {"discovered": 2, "fetched": 2, "parsed": 1, "failed": 1, "search_failed": 0, "cache_hits": 0}
    assert len(jobs) == 1 and jobs[0].source_url == url("good123")
    assert jobs[0].internship_days_per_week == 2  # Search card said 5; detail said 2.
    assert f"[warning] shixiseng parse failed: {url('bad123')}" in capsys.readouterr().err


@pytest.mark.parametrize("status", [403, 429])
def test_access_restriction_stops_collection(monkeypatch, status):
    monkeypatch.setattr(shixiseng, "KEYWORDS", ("法务",))
    monkeypatch.setattr(shixiseng, "CITIES", ("广州",))

    class BlockedHttp:
        def get(self, requested, **kwargs):
            return type("Response", (), {"status_code": status, "content": b""})()

    collector = ShixisengCollector(max_jobs=10, http=BlockedHttp())
    assert collector.collect() == []
    assert collector.blocked_reason == f"HTTP {status} at {shixiseng.SEARCH_URL}"
    assert collector.stats["fetched"] == 0


def test_verification_page_stops_collection(monkeypatch):
    monkeypatch.setattr(shixiseng, "KEYWORDS", ("法务",))
    monkeypatch.setattr(shixiseng, "CITIES", ("广州",))

    class ChallengeHttp:
        def get(self, requested, **kwargs):
            page = "<html><head><title>安全验证</title></head><body>请输入验证码</body></html>"
            return type("Response", (), {"status_code": 200, "content": page.encode("utf-8")})()

    collector = ShixisengCollector(max_jobs=10, http=ChallengeHttp())
    assert collector.collect() == []
    assert "verification page" in collector.blocked_reason


def test_real_structure_deadline_is_parsed_and_expired():
    parsed = parse_detail(html("deadline_real_structure"), url("deadline123"))
    assert parsed.deadline == date(2026, 9, 30)
    job = normalize_jobs([parsed])[0]
    assert job.refreshed_at == datetime(2023, 9, 24, 9, 38, 32)
    counts = {}
    assert filter_jobs([job], profile(), today=date(2026, 10, 5), rejection_counts=counts) == []
    assert counts == {"expired": 1}


def test_future_deadline_is_retained_with_staleness_warning():
    page = html("deadline_real_structure").replace("2026-09-30", "2026-10-20")
    job = normalize_jobs([parse_detail(page, url("future123"))])[0]
    accepted = filter_jobs([job], profile(), today=date(2026, 10, 5))
    assert len(accepted) == 1
    assert accepted[0].deadline == date(2026, 10, 20)
    assert "页面刷新时间较早，需确认岗位是否仍有效" in accepted[0].risk_reasons


def test_deadline_fallback_searches_recruitment_text():
    page = html("deadline_real_structure").replace(
        '<div class="con-job"><div class="job_til">投递要求：</div><div>简历要求：不限</div><div class="cutom_font">截止日期：2026-09-30</div></div>',
        '<div class="apply-meta">截止日期：2026-09-30</div>',
    )
    assert parse_detail(page, url("fallback123")).deadline == date(2026, 9, 30)


@pytest.mark.parametrize("marker", ["当前职位已下线", "该职位已下线", "职位已下线"])
def test_offline_marker_wins_over_apply_button(marker):
    page = html("deadline_real_structure").replace("<aside>", f"<div>{marker}</div><aside>")
    job = normalize_jobs([parse_detail(page, url("offlineprecedence123"))])[0]
    assert job.is_active is False
    counts = {}
    assert filter_jobs([job], profile(), today=date(2026, 10, 5), rejection_counts=counts) == []
    assert counts == {"inactive": 1}
