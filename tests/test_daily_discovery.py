from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

import pytest
import yaml

import collectors.shixiseng as shixiseng
from collectors.shixiseng import ShixisengCollector, parse_detail
from pipeline.discovery import classify_jobs, content_hash, job_key, load_state, save_state
from pipeline.evidence import extract_tags
from pipeline.normalize import normalize_jobs
from pipeline.rank import score_job
from reports.generator import generate_report


FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 5)
NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


def profile() -> dict:
    return yaml.safe_load(Path("config/profile.example.yaml").read_text(encoding="utf-8"))


def sample_job():
    html = (FIXTURES / "shixiseng_normal.html").read_text(encoding="utf-8")
    url = "https://www.shixiseng.com/intern/inn_daily123"
    return normalize_jobs([parse_detail(html, url)])[0]


def test_legal_research_and_drafting_have_literal_evidence():
    business, tasks, evidence = extract_tags("岗位：投融资并购；工作：法律研究、文件起草。")
    assert "并购" in business
    assert "法律研究" in tasks and "文书起草" in tasks
    assert all(item in "岗位：投融资并购；工作：法律研究、文件起草。" for item in evidence)


def test_business_and_task_synonyms_are_normalized_without_guessing():
    text = "公司合规、商事争议解决、数据保护、专利、IPO、反垄断、银行金融。合同审阅、案件材料整理、监管政策跟踪、客户沟通。"
    business, tasks, _ = extract_tags(text)
    assert {"合规", "商事争议", "数据合规", "知识产权", "资本市场", "反垄断", "金融"} <= set(business)
    assert {"合同审查", "案件支持", "法规研究", "客户沟通"} <= set(tasks)
    assert "纯行政" not in tasks and "销售" not in tasks


def test_research_and_search_do_not_double_count_content():
    job = sample_job()
    one = score_job(replace(job, task_tags=["法律研究"]), profile(), today=TODAY)
    two = score_job(replace(job, task_tags=["法律研究", "法律检索"]), profile(), today=TODAY)
    assert one.content_score == two.content_score


def test_ordinary_material_sorting_is_not_negative():
    _, tasks, _ = extract_tags("协助整理材料。")
    assert "纯行政" not in tasks and "案件支持" not in tasks


def test_old_refresh_receives_freshness_penalty():
    job = sample_job()
    fresh = score_job(replace(job, refreshed_at=datetime(2026, 10, 5)), profile(), today=TODAY)
    old = score_job(replace(job, refreshed_at=datetime(2023, 9, 24)), profile(), today=TODAY)
    unknown = score_job(replace(job, refreshed_at=None), profile(), today=TODAY)
    assert (fresh.freshness_status, fresh.freshness_adjustment) == ("fresh", 0)
    assert (old.freshness_status, old.freshness_adjustment) == ("very_stale", -8)
    assert (unknown.freshness_status, unknown.freshness_adjustment) == ("unknown", -2)
    assert old.base_match_score == fresh.base_match_score
    assert old.match_score == fresh.match_score - 8


@pytest.mark.parametrize(
    ("days_ago", "expected"),
    [(30, "fresh"), (31, "recent"), (90, "recent"), (91, "stale"), (180, "stale"), (181, "very_stale")],
)
def test_freshness_boundaries(days_ago, expected):
    job = replace(sample_job(), refreshed_at=datetime.combine(TODAY - timedelta(days=days_ago), datetime.min.time()))
    assert score_job(job, profile(), today=TODAY).freshness_status == expected


def test_state_initializes_when_file_is_missing():
    assert load_state(Path("data/state/nonexistent_test_state.json")) == {"version": 1, "jobs": {}}


def test_missing_source_id_uses_canonical_url():
    job = replace(sample_job(), source_job_id=None, source_url="https://www.shixiseng.com/intern/inn_daily123?pcm=tracking")
    assert job_key(job) == "shixiseng:url:https://www.shixiseng.com/intern/inn_daily123"


def test_state_persists_across_process_runs():
    path = Path("data/.pytest_tmp/discovery_state_test.json")
    first, state = classify_jobs([score_job(sample_job(), profile(), today=TODAY)], load_state(path), NOW)
    try:
        save_state(path, state)
        second, _ = classify_jobs([score_job(sample_job(), profile(), today=TODAY)], load_state(path), NOW + timedelta(hours=1))
    finally:
        path.unlink(missing_ok=True)
    assert first[0].discovery_status == "new"
    assert second[0].discovery_status == "seen"


def test_first_then_second_run_then_deadline_change():
    job = score_job(sample_job(), profile(), today=TODAY)
    state = {"version": 1, "jobs": {}}
    first, state = classify_jobs([job], state, NOW)
    assert first[0].discovery_status == "new"
    key = "shixiseng:inn_daily123"
    assert state["jobs"][key]["first_seen_at"] == NOW.isoformat()
    second_job = replace(job, collected_at=NOW + timedelta(hours=1))
    second, state = classify_jobs([second_job], state, NOW + timedelta(hours=1))
    assert second[0].discovery_status == "seen"
    assert second[0].changes == []
    changed = replace(job, deadline=date(2026, 10, 20), raw_text=job.raw_text.replace("2026-12-31", "2026-10-20"))
    third, state = classify_jobs([changed], state, NOW + timedelta(hours=2))
    assert third[0].discovery_status == "updated"
    assert "deadline: 2026-12-31 → 2026-10-20" in third[0].changes
    assert state["jobs"][key]["first_seen_at"] == NOW.isoformat()


def test_content_hash_ignores_collection_and_refresh_timestamps():
    job = sample_job()
    changed = replace(
        job, collected_at=NOW + timedelta(days=1),
        refreshed_at=datetime(2026, 10, 6),
        raw_text=job.raw_text.replace("2026-10-05 刷新", "2026-10-06 刷新"),
    )
    assert content_hash(job) == content_hash(changed)


def test_body_change_is_updated_without_inventing_field_change():
    job = score_job(sample_job(), profile(), today=TODAY)
    _, state = classify_jobs([job], {"version": 1, "jobs": {}}, NOW)
    changed = replace(job, raw_text=job.raw_text.replace("合同审查", "合同起草"))
    updated, _ = classify_jobs([changed], state, NOW + timedelta(hours=1))
    assert updated[0].discovery_status == "updated"
    assert updated[0].changes == ["招聘正文或基本信息已更新"]


def test_five_day_high_value_job_is_schedule_conflict():
    job = sample_job()
    job = replace(job, internship_days_per_week=5, business_tags=["涉外法律"])
    ranked = score_job(job, profile(), today=TODAY)
    assert ranked.direction_score >= 17 and ranked.content_score >= 10
    assert ranked.convenience_score == 0 and ranked.schedule_conflict is True


def test_report_sections_separate_new_updated_seen_and_conflict():
    base = score_job(sample_job(), profile(), today=TODAY)
    new = replace(base, id="new", discovery_status="new")
    updated = replace(base, id="updated", title="变化岗位", discovery_status="updated", changes=["deadline: 2026-09-30 → 2026-12-31"])
    seen = replace(base, id="seen", title="已见岗位", discovery_status="seen", schedule_conflict=True)
    path = Path("data/test_daily_discovery_report.md")
    try:
        report = generate_report([new, updated, seen], 3, path, updated_jobs=[updated], tracked_total=3).read_text(encoding="utf-8")
    finally:
        path.unlink(missing_ok=True)
    assert "## 今日新发现" in report and "## 岗位发生变化" in report
    assert "## 时间不合适但值得关注" in report and "## 已见岗位" in report
    new_section = report.split("## 今日新发现", 1)[1].split("## 岗位发生变化", 1)[0]
    assert "变化岗位" not in new_section and "已见岗位" not in new_section
    assert "deadline: 2026-09-30 → 2026-12-31" in report
    assert "机会本身值得看，但与你当前可投入时间冲突" in report
    assert "已跟踪 3 个岗位" in report


def test_detail_cache_reuses_recent_html_then_expires(monkeypatch):
    monkeypatch.setattr(shixiseng, "KEYWORDS", ("法务",))
    monkeypatch.setattr(shixiseng, "CITIES", ("广州",))
    monkeypatch.setattr(shixiseng.time, "sleep", lambda _: None)
    url = "https://www.shixiseng.com/intern/inn_cache123"
    detail = (FIXTURES / "shixiseng_normal.html").read_text(encoding="utf-8")
    search = f'<a href="{url}">法务实习生</a>'

    class FakeHttp:
        detail_calls = 0

        def get(self, requested, **kwargs):
            if requested == url:
                self.detail_calls += 1
            content = search if requested == shixiseng.SEARCH_URL else detail
            return type("Response", (), {"status_code": 200, "content": content.encode("utf-8")})()

    cache_dir = Path("data/.pytest_tmp/cache_test")
    http = FakeHttp()
    try:
        first = ShixisengCollector(max_jobs=1, http=http, cache_dir=cache_dir)
        assert len(first.collect()) == 1 and first.stats["cache_hits"] == 0
        second = ShixisengCollector(max_jobs=1, http=http, cache_dir=cache_dir)
        assert len(second.collect()) == 1 and second.stats["cache_hits"] == 1
        assert http.detail_calls == 1
        cache_path = cache_dir / "inn_cache123.json"
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        payload["last_checked"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        third = ShixisengCollector(max_jobs=1, http=http, cache_dir=cache_dir)
        assert len(third.collect()) == 1 and third.stats["cache_hits"] == 0
        assert http.detail_calls == 2
    finally:
        cache_path = cache_dir / "inn_cache123.json"
        cache_path.unlink(missing_ok=True)
        if cache_dir.exists():
            cache_dir.rmdir()


def test_two_search_pages_deduplicate_discovered_urls(monkeypatch):
    monkeypatch.setattr(shixiseng, "KEYWORDS", ("法务",))
    monkeypatch.setattr(shixiseng, "CITIES", ("广州",))
    monkeypatch.setattr(shixiseng.time, "sleep", lambda _: None)
    first_url = "https://www.shixiseng.com/intern/inn_pagefirst"
    second_url = "https://www.shixiseng.com/intern/inn_pagesecond"
    detail = (FIXTURES / "shixiseng_normal.html").read_text(encoding="utf-8")

    class FakeHttp:
        search_pages = []

        def get(self, requested, **kwargs):
            if requested == shixiseng.SEARCH_URL:
                page = kwargs["params"].get("page", 1)
                self.search_pages.append(page)
                if page == 1:
                    content = f'<a href="{first_url}">first</a><div class="el-pagination"><button class="btn-next">next</button></div>'
                else:
                    content = f'<a href="{first_url}">same</a><a href="{second_url}">second</a><div class="el-pagination"><button class="btn-next" disabled>next</button></div>'
            else:
                content = detail
            return type("Response", (), {"status_code": 200, "content": content.encode("utf-8")})()

    http = FakeHttp()
    collector = ShixisengCollector(max_jobs=10, pages=2, http=http)
    assert len(collector.collect()) == 2
    assert collector.stats["discovered"] == 2
    assert http.search_pages == [1, 2]
