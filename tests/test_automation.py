from dataclasses import replace
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys

import pytest
import yaml

import main as app_main
from automation.github_actions import ISSUE_TITLE, notify_issue, write_profile
from collectors.shixiseng import parse_detail
from pipeline.discovery import classify_jobs
from pipeline.normalize import normalize_jobs
from pipeline.rank import score_job
from reports.summary import (
    build_issue_comment, build_run_summary, collection_status,
    render_actions_summary, should_notify, write_run_summary,
)


FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)


def profile() -> dict:
    return yaml.safe_load(Path("config/profile.example.yaml").read_text(encoding="utf-8"))


def job(status: str = "new"):
    html = (FIXTURES / "shixiseng_normal.html").read_text(encoding="utf-8")
    parsed = parse_detail(html, "https://www.shixiseng.com/intern/inn_automation123")
    ranked = score_job(normalize_jobs([parsed])[0], profile(), today=NOW.date())
    return replace(ranked, discovery_status=status)


def test_new_job_triggers_notification():
    summary = build_run_summary(status="success", collected=1, accepted=[job("new")])
    assert summary["new"] == 1 and should_notify(summary)
    assert "### 新岗位" in build_issue_comment(summary, date(2026, 10, 9))


def test_updated_job_triggers_notification_with_changes():
    updated = replace(job("updated"), changes=["deadline: 2026-09-30 → 2026-12-31"])
    summary = build_run_summary(status="success", collected=1, accepted=[updated])
    comment = build_issue_comment(summary, date(2026, 10, 9))
    assert summary["updated"] == 1 and should_notify(summary)
    assert "deadline: 2026-09-30 → 2026-12-31" in comment


def test_seen_only_does_not_notify():
    summary = build_run_summary(status="success", collected=1, accepted=[job("seen")])
    assert summary["new"] == summary["updated"] == 0
    assert not should_notify(summary)
    assert build_issue_comment(summary, date(2026, 10, 9)) == ""
    assert notify_issue(summary, "", "") is False


def test_blocked_status_does_not_claim_no_new_jobs():
    status = collection_status(blocked_reason="HTTP 403 at public search page", collected=0)
    summary = build_run_summary(status=status, collected=0, accepted=[], detail="HTTP 403")
    markdown = render_actions_summary(summary)
    assert status == "blocked" and not should_notify(summary)
    assert "今日采集失败或被限制" in markdown
    assert "新岗位：未统计" in markdown
    assert "今天没有新岗位" not in markdown


def test_partial_and_failed_collection_statuses():
    assert collection_status(search_failures=1, collected=3, normalized=3) == "partial"
    assert collection_status(detail_failures=3, collected=0, normalized=0) == "failed"
    assert collection_status(unexpected_error=True) == "failed"
    partial = build_run_summary(status="partial", collected=3, accepted=[])
    assert "采集不完整" in render_actions_summary(partial)


def test_run_summary_json_contains_required_fields():
    summary = build_run_summary(status="success", collected=1, accepted=[job("new")])
    path = Path("data/.pytest_tmp/run_summary_test.json")
    try:
        write_run_summary(path, summary)
        saved = json.loads(path.read_text(encoding="utf-8"))
    finally:
        path.unlink(missing_ok=True)
    assert {"collection_status", "collected", "accepted", "new", "updated", "seen", "schedule_conflict", "top_jobs"} <= saved.keys()
    assert saved["top_jobs"][0]["company"] == "测试公司甲"
    assert {"company", "title", "score", "url", "discovery_status"} <= saved["top_jobs"][0].keys()


def test_restored_state_changes_new_to_seen_in_summary():
    ranked = job()
    first, state = classify_jobs([ranked], {"version": 1, "jobs": {}}, NOW)
    second, _ = classify_jobs([ranked], state, NOW)
    first_summary = build_run_summary(status="success", collected=1, accepted=first)
    second_summary = build_run_summary(status="success", collected=1, accepted=second)
    assert (first_summary["new"], first_summary["seen"]) == (1, 0)
    assert (second_summary["new"], second_summary["seen"]) == (0, 1)


def test_missing_profile_secret_fails_without_showing_contents():
    path = Path("data/.pytest_tmp/profile_test.yaml")
    with pytest.raises(ValueError, match="PROFILE_YAML"):
        write_profile(None, path)
    with pytest.raises(ValueError, match="invalid YAML") as error:
        write_profile("secret-text: [not closed", path)
    assert "secret-text" not in str(error.value)
    assert not path.exists()


def test_issue_notification_reuses_fixed_issue_without_network():
    summary = build_run_summary(status="success", collected=1, accepted=[job("new")])

    class Response:
        def __init__(self, value):
            self.value = value

        def raise_for_status(self):
            pass

        def json(self):
            return self.value

    class FakeSession:
        calls = []

        def request(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            if method == "GET":
                return Response([{"title": ISSUE_TITLE, "number": 7, "state": "open"}])
            return Response({"id": 1})

    fake = FakeSession()
    assert notify_issue(summary, "owner/repository", "fake-token", session=fake, today=date(2026, 10, 9))
    assert [call[0] for call in fake.calls] == ["GET", "POST"]
    assert fake.calls[1][1].endswith("/issues/7/comments")
    assert "2026-10-09 实习更新" in fake.calls[1][2]["json"]["body"]


def test_issue_notification_creates_fixed_issue_if_missing():
    summary = build_run_summary(status="success", collected=1, accepted=[job("new")])

    class Response:
        def __init__(self, value):
            self.value = value

        def raise_for_status(self):
            pass

        def json(self):
            return self.value

    class FakeSession:
        def __init__(self):
            self.calls = []

        def request(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            if method == "GET":
                return Response([])
            if url.endswith("/issues"):
                return Response({"number": 8, "state": "open"})
            return Response({"id": 2})

    fake = FakeSession()
    assert notify_issue(summary, "owner/repository", "fake-token", session=fake, today=date(2026, 10, 9))
    assert [call[0] for call in fake.calls] == ["GET", "POST", "POST"]
    assert fake.calls[1][2]["json"]["title"] == ISSUE_TITLE
    assert fake.calls[2][1].endswith("/issues/8/comments")


def test_blocked_main_writes_failure_summary_and_report(monkeypatch):
    root = Path("data/.pytest_tmp/blocked_run")

    class BlockedCollector:
        blocked_reason = "HTTP 429 at public search page"
        stats = {"discovered": 0, "fetched": 0, "parsed": 0, "failed": 0, "search_failed": 0}

        def collect(self):
            return []

    monkeypatch.setattr(app_main, "ROOT", root)
    monkeypatch.setattr(app_main, "load_profile", profile)
    monkeypatch.setattr(app_main, "ShixisengCollector", lambda **kwargs: BlockedCollector())
    monkeypatch.setattr(sys, "argv", ["main.py"])
    try:
        with pytest.raises(SystemExit) as result:
            app_main.main()
        summary = json.loads((root / "data/run_summary.json").read_text(encoding="utf-8"))
        report = (root / "data/daily_report.md").read_text(encoding="utf-8")
    finally:
        (root / "data/run_summary.json").unlink(missing_ok=True)
        (root / "data/daily_report.md").unlink(missing_ok=True)
        if (root / "data").exists():
            (root / "data").rmdir()
        if root.exists():
            root.rmdir()
    assert result.value.code == 1
    assert summary["collection_status"] == "blocked"
    assert "今日采集失败或被限制" in report
    assert "今天没有新发现" not in report


def test_workflow_has_schedule_secret_cache_artifact_and_issue_permissions():
    workflow = yaml.load(Path(".github/workflows/daily-internships.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["on"]["schedule"][0] == {"cron": "0 12 * * *", "timezone": "Asia/Shanghai"}
    assert workflow["permissions"] == {"contents": "read", "issues": "write"}
    assert workflow["concurrency"] == {"group": "internship-agent-daily", "cancel-in-progress": "false"}
    steps = workflow["jobs"]["daily"]["steps"]
    uses = [step.get("uses", "") for step in steps]
    assert "actions/cache/restore@v4" in uses and "actions/cache/save@v4" in uses
    assert "actions/upload-artifact@v4" in uses
    assert any(step.get("env", {}).get("PROFILE_YAML") == "${{ secrets.PROFILE_YAML }}" for step in steps)
    assert any(step.get("continue-on-error") == "true" and "notify" in step.get("run", "") for step in steps)
    cache_steps = [step for step in steps if step.get("uses", "").startswith("actions/cache/")]
    assert cache_steps[0]["with"]["key"] == cache_steps[1]["with"]["key"]
    assert "github.run_id" in cache_steps[0]["with"]["key"]
    assert any(step.get("if") == "always()" and "summary" in step.get("run", "") for step in steps)
