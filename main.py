import argparse
from datetime import datetime
from pathlib import Path

import yaml

from collectors.mock_collector import MockCollector
from collectors.shixiseng import ShixisengCollector
from pipeline.deduplicate import deduplicate_jobs
from pipeline.discovery import classify_jobs, load_state, save_state
from pipeline.filter import filter_jobs
from pipeline.normalize import normalize_jobs
from pipeline.rank import rank_jobs
from reports.generator import generate_report


ROOT = Path(__file__).resolve().parent
FIELD_COVERAGE = (
    ("title", "title"), ("company", "company"), ("location", "location"),
    ("education", "education"), ("days_per_week", "internship_days_per_week"),
    ("duration", "internship_duration"), ("deadline", "deadline"),
    ("remote", "remote"), ("is_active", "is_active"),
)


def print_field_coverage(jobs: list) -> None:
    total = len(jobs)
    for label, attr in FIELD_COVERAGE:
        known = sum(getattr(job, attr) is not None and getattr(job, attr) != "" for job in jobs)
        percentage = 100 * known / total if total else 0.0
        print(f"[field coverage] {label}: {known}/{total} ({percentage:.1f}%)")


def load_profile() -> dict:
    path = ROOT / "config" / "profile.yaml"
    if not path.exists():
        raise FileNotFoundError("Missing config/profile.yaml. Copy config/profile.example.yaml first.")
    with path.open(encoding="utf-8") as file:
        profile = yaml.safe_load(file)
    if not isinstance(profile, dict):
        raise ValueError("config/profile.yaml must contain a YAML mapping")
    required = {"education", "skills", "background", "preferred_directions", "location", "availability", "preferences"}
    missing = required - profile.keys()
    if missing:
        raise ValueError(
            f"Missing v0.2 profile settings: {', '.join(sorted(missing))}. "
            "Update config/profile.yaml using config/profile.example.yaml."
        )
    try:
        profile["education"]["major"]
        profile["education"]["grade"]
        profile["education"]["degree"]
        profile["preferred_directions"]["high"]
        profile["preferred_directions"]["medium"]
        profile["location"]["preferred"]
        profile["location"]["acceptable"]
        profile["location"]["remote_allowed"]
        profile["availability"]["preferred_days_per_week"]
        profile["availability"]["max_days_per_week"]
        profile["preferences"]["avoid"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Invalid v0.2 profile setting: {exc}") from exc
    return profile


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an internship recommendation report")
    parser.add_argument("--source", choices=("shixiseng", "mock"), default="shixiseng")
    parser.add_argument("--max-jobs", type=int, default=30, help="Maximum Shixiseng detail pages to fetch")
    parser.add_argument("--pages", type=int, default=1, help="Maximum public search pages per keyword/city")
    args = parser.parse_args()

    profile = load_profile()
    collector = MockCollector() if args.source == "mock" else ShixisengCollector(
        max_jobs=args.max_jobs, pages=args.pages, cache_dir=ROOT / "data" / "cache" / "shixiseng",
    )
    jobs = collector.collect()
    collected_count = len(jobs)
    print(f"[collect] {collected_count} jobs")

    jobs = normalize_jobs(jobs)
    print(f"[normalize] {len(jobs)} jobs")
    print_field_coverage(jobs)

    jobs = deduplicate_jobs(jobs)
    print(f"[deduplicate] {len(jobs)} jobs")

    now = datetime.now().astimezone()
    jobs = rank_jobs(jobs, profile, today=now.date())
    print("[rank] completed")
    state_path = ROOT / "data" / "state" / "jobs.json"
    state = load_state(state_path) if args.source == "shixiseng" else {"version": 1, "jobs": {}}
    jobs, next_state = classify_jobs(jobs, state, now)
    for status in ("new", "updated", "seen"):
        print(f"[discovery] {status}: {sum(job.discovery_status == status for job in jobs)}")

    rejection_counts = {key: 0 for key in ("expired", "inactive", "major_mismatch", "location_mismatch")}
    accepted = filter_jobs(jobs, profile, today=now.date(), rejection_counts=rejection_counts)
    print(f"[filter] {len(accepted)} jobs")
    for reason, count in rejection_counts.items():
        print(f"[filter] {reason}: {count}")
    print(f"[filter] accepted: {len(accepted)}")
    print(f"[discovery] schedule_conflict: {sum(job.schedule_conflict for job in accepted)}")

    report_path = generate_report(
        accepted, collected_count=collected_count, output_path=ROOT / "data" / "daily_report.md",
        updated_jobs=[job for job in jobs if job.discovery_status == "updated"],
        tracked_total=len(next_state["jobs"]),
    )
    if args.source == "shixiseng":
        save_state(state_path, next_state)
    print(f"[report] {report_path.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
