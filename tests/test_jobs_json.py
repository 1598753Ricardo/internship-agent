from dataclasses import replace
from datetime import date
import json
from pathlib import Path
import sys

import yaml

import main as app_main
from collectors.mock_collector import MockCollector
from reports.jobs_json import write_jobs_json


def test_jobs_json_preserves_job_fields_and_unknown_values(tmp_path):
    job = replace(
        MockCollector().collect()[0],
        remote=None,
        deadline=date(2026, 12, 31),
        match_score=92,
        recommendation="强烈推荐",
        match_reasons=["专业符合明确要求"],
        risk_reasons=["需确认工作时间"],
        requirements=["法学本科"],
        business_tags=["涉外法律"],
        task_tags=["法律检索"],
    )
    path = tmp_path / "data" / "output" / "jobs.json"
    assert write_jobs_json(path, [job]) == path
    assert json.loads(path.read_text(encoding="utf-8")) == [{
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote": None,
        "match_score": 92,
        "recommendation": "强烈推荐",
        "match_reasons": ["专业符合明确要求"],
        "risk_reasons": ["需确认工作时间"],
        "requirements": ["法学本科"],
        "deadline": "2026-12-31",
        "source_url": job.source_url,
        "business_tags": ["涉外法律"],
        "task_tags": ["法律检索"],
    }]
    write_jobs_json(path, [replace(job, deadline=None, remote=False)])
    saved = json.loads(path.read_text(encoding="utf-8"))[0]
    assert saved["deadline"] == ""
    assert saved["remote"] is False


def test_mock_main_writes_json_alongside_existing_outputs(monkeypatch, tmp_path):
    profile = yaml.safe_load(Path("config/profile.example.yaml").read_text(encoding="utf-8"))
    monkeypatch.setattr(app_main, "ROOT", tmp_path)
    monkeypatch.setattr(app_main, "load_profile", lambda: profile)
    monkeypatch.setattr(sys, "argv", ["main.py", "--source", "mock"])

    app_main.main()

    report = (tmp_path / "data" / "daily_report.md").read_text(encoding="utf-8")
    summary = json.loads((tmp_path / "data" / "run_summary.json").read_text(encoding="utf-8"))
    jobs = json.loads((tmp_path / "data" / "output" / "jobs.json").read_text(encoding="utf-8"))
    assert "今日最值得看" in report
    assert summary["collection_status"] == "success"
    assert len(jobs) == summary["accepted"]
    assert {job["id"] for job in jobs}.isdisjoint({"expired", "unrelated", "wrong-city"})
    assert all(isinstance(job["match_score"], int) and job["recommendation"] for job in jobs)
    assert all(isinstance(job["match_reasons"], list) and isinstance(job["requirements"], list) for job in jobs)
