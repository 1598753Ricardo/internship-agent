from pathlib import Path

import yaml

from collectors.mock_collector import MockCollector
from pipeline.deduplicate import deduplicate_jobs
from pipeline.filter import filter_jobs
from pipeline.normalize import normalize_jobs
from pipeline.rank import rank_jobs
from reports.generator import generate_report


ROOT = Path(__file__).resolve().parent


def load_profile() -> dict:
    path = ROOT / "config" / "profile.yaml"
    if not path.exists():
        raise FileNotFoundError("Missing config/profile.yaml. Copy config/profile.example.yaml first.")
    with path.open(encoding="utf-8") as file:
        profile = yaml.safe_load(file)
    if not isinstance(profile, dict):
        raise ValueError("config/profile.yaml must contain a YAML mapping")
    required = {"education", "preferred_locations", "remote_allowed", "preferred_directions", "availability", "skills"}
    missing = required - profile.keys()
    if missing:
        raise ValueError(f"Missing profile settings: {', '.join(sorted(missing))}")
    return profile


def main() -> None:
    profile = load_profile()
    jobs = MockCollector().collect()
    collected_count = len(jobs)
    print(f"[collect] {collected_count} jobs")

    jobs = normalize_jobs(jobs)
    print(f"[normalize] {len(jobs)} jobs")

    jobs = deduplicate_jobs(jobs)
    print(f"[deduplicate] {len(jobs)} jobs")

    jobs = filter_jobs(jobs, profile)
    print(f"[filter] {len(jobs)} jobs")

    jobs = rank_jobs(jobs, profile)
    print("[rank] completed")

    report_path = generate_report(jobs, collected_count=collected_count, output_path=ROOT / "data" / "daily_report.md")
    print(f"[report] {report_path.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
