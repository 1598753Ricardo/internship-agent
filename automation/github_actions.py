"""Write the private profile, Actions summary, and fixed daily Issue."""

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

from reports.summary import build_issue_comment, render_actions_summary, should_notify


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "data" / "run_summary.json"
ISSUE_TITLE = "Internship Agent Daily"


def write_profile(value: str | None, path: Path) -> None:
    if not value or not value.strip():
        raise ValueError("Missing Repository Secret PROFILE_YAML.")
    try:
        parsed = yaml.safe_load(value)
    except yaml.YAMLError:
        raise ValueError("PROFILE_YAML is invalid YAML; check the repository secret.") from None
    if not isinstance(parsed, dict):
        raise ValueError("PROFILE_YAML must contain a YAML mapping.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip("\n") + "\n", encoding="utf-8")


def write_actions_summary(path: Path, summary_path: Path = SUMMARY_PATH) -> None:
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        content = render_actions_summary(summary)
    else:
        content = "# Internship Agent 每日运行\n\n**运行在生成采集摘要前失败；请查看本次 Actions 日志。**\n"
    with path.open("a", encoding="utf-8") as file:
        file.write(content + "\n")


def notify_issue(
    summary: dict, repository: str, token: str,
    session: requests.Session | None = None, today=None,
) -> bool:
    if not should_notify(summary):
        return False
    if not repository or len(repository.split("/")) != 2 or not token:
        raise ValueError("GITHUB_REPOSITORY and GITHUB_TOKEN are required for Issue notification")
    client = session or requests.Session()
    base = f"https://api.github.com/repos/{repository}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    def api(method: str, path: str, **kwargs):
        response = client.request(method, base + path, headers=headers, timeout=20, **kwargs)
        response.raise_for_status()
        return response.json()

    issue = None
    for page in range(1, 101):
        listed = api("GET", "/issues", params={"state": "all", "per_page": 100, "page": page})
        issue = next((item for item in listed if item.get("title") == ISSUE_TITLE and "pull_request" not in item), None)
        if issue is not None or len(listed) < 100:
            break
    if issue is None:
        issue = api("POST", "/issues", json={
            "title": ISSUE_TITLE,
            "body": "Internship Agent 每日岗位变化摘要。完整日报可在对应 Actions 运行的 Artifact 下载。",
        })
    elif issue.get("state") == "closed":
        api("PATCH", f"/issues/{issue['number']}", json={"state": "open"})

    date = today or datetime.now(timezone(timedelta(hours=8))).date()
    api("POST", f"/issues/{issue['number']}/comments", json={"body": build_issue_comment(summary, date)})
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="GitHub Actions helpers")
    parser.add_argument("command", choices=("write-profile", "summary", "notify"))
    args = parser.parse_args()
    if args.command == "write-profile":
        try:
            write_profile(os.environ.get("PROFILE_YAML"), ROOT / "config" / "profile.yaml")
        except ValueError as exc:
            raise SystemExit(str(exc)) from None
        print("[profile] config/profile.yaml created from Repository Secret")
    elif args.command == "summary":
        destination = os.environ.get("GITHUB_STEP_SUMMARY")
        if not destination:
            raise SystemExit("GITHUB_STEP_SUMMARY is not set")
        write_actions_summary(Path(destination))
        print("[summary] GitHub Actions Summary written")
    else:
        if not SUMMARY_PATH.exists():
            print("[issue] run summary missing; skipping notification")
            return
        summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        sent = notify_issue(summary, os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_TOKEN", ""))
        print("[issue] comment posted" if sent else "[issue] no actionable changes; skipped")


if __name__ == "__main__":
    main()
